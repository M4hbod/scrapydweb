# coding: utf-8
"""Sync upsert of scrapyd's /jobs into the per-node Job table.

Sync twin of the async helpers in routers/jobs.py, so the background stats
collector (which already fetches + parses /jobs every cycle) keeps the Job
table fresh -- update_time, status, pages/items, finish -- without depending on
a browser page view or a self-HTTP snapshot call. Everything here runs in the
collector's thread on a sync SQLAlchemy session.
"""
import logging
import re
from datetime import datetime

from sqlalchemy import select

from ..routers.jobs import (DELETED, HREF_PATTERN, NOT_DELETED, STATUS_FINISHED,
                            STATUS_PENDING, STATUS_RUNNING)
from ..vars import jobs_table_map

logger = logging.getLogger(__name__)


def _upsert(s, Job, jobs, liststats):
    for job in jobs:
        record = s.execute(select(Job).filter_by(
            project=job['project'], spider=job['spider'], job=job['job'])).scalar_one_or_none()
        if record:
            if record.deleted == DELETED:
                if record.status == STATUS_FINISHED and str(record.start) == job['start']:
                    continue
                record.deleted, record.pages, record.items = NOT_DELETED, None, None
        else:
            record = Job()
            s.add(record)
        for k, v in job.items():
            v = v or None
            if k in ('start', 'finish'):
                v = datetime.strptime(v, '%Y-%m-%d %H:%M:%S') if v else None
            elif k == 'pid':
                v = int(v) if v else None
            elif k in ('href_log', 'href_items'):
                m = re.search(HREF_PATTERN, v) if v else None
                v = m.group(1) if m else v
            setattr(record, k, v)
        if not job['start']:
            record.status = STATUS_PENDING
        elif not job['finish']:
            record.status = STATUS_RUNNING
        else:
            record.status = STATUS_FINISHED
        if not job['start']:
            record.pages = record.items = None
        elif liststats:
            try:
                d = liststats[job['project']][job['spider']][job['job']]
                record.pages, record.items = d['pages'], d['items']
            except (KeyError, TypeError):
                pass
        record.update_time = datetime.now()


def _clean_pending(s, Job, all_jobs):
    current = [(j['project'], j['spider'], j['job']) for j in all_jobs if not j['start']]
    for record in s.execute(select(Job).filter_by(start=None)).scalars().all():
        if (record.project, record.spider, record.job) not in current:
            s.delete(record)


def _finalize_stale(s, Job, all_jobs, liststats):
    # running rows scrapyd no longer lists -> mark finished, take finish data from logparser
    current = {(j['project'], j['spider'], j['job']) for j in all_jobs}
    for r in s.execute(select(Job).filter_by(deleted='0', status=STATUS_RUNNING)).scalars().all():
        if (r.project, r.spider, r.job) in current:
            continue
        r.status, r.pid = STATUS_FINISHED, None
        try:
            d = liststats[r.project][r.spider][r.job]
            r.pages, r.items = d['pages'], d['items']
            r.runtime = d.get('runtime') or r.runtime
            lt = d.get('latest_log_time')
            if lt:
                r.finish = datetime.strptime(lt, '%Y-%m-%d %H:%M:%S')
        except (KeyError, TypeError, ValueError):
            pass
        if r.finish is None:
            r.finish = r.update_time


def sync_server_jobs(s, server, node, all_jobs, liststats):
    """Upsert + clean + finalize the per-node Job table from a parsed /jobs list.
    Caller commits the session."""
    Job = jobs_table_map.get(node)
    if Job is None:
        from ..models import create_jobs_table
        from ..vars import STRICT_NAME_PATTERN
        Job = create_jobs_table(re.sub(STRICT_NAME_PATTERN, '_', server))
        jobs_table_map[node] = Job
    _upsert(s, Job, all_jobs, liststats)
    _clean_pending(s, Job, all_jobs)
    _finalize_stale(s, Job, all_jobs, liststats)
