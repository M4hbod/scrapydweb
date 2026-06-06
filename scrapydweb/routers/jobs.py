# coding: utf-8
"""Jobs persistence helpers (parse scrapyd /jobs HTML, upsert into the per-node table).

Shared by routers.apiv2 and services.dashboard."""
from collections import OrderedDict
from datetime import datetime
import re

from sqlalchemy import func, select


STATUS_PENDING, STATUS_RUNNING, STATUS_FINISHED = '0', '1', '2'
NOT_DELETED, DELETED = '0', '1'
NA = 'N/A'
HREF_PATTERN = re.compile(r"""href=['"](.+?)['"]""")
JOB_PATTERN = re.compile(r"""
    <tr>\s*<td>(?P<Project>.*?)</td>\s*<td>(?P<Spider>.*?)</td>\s*<td>(?P<Job>.*?)</td>\s*
    (?:<td>(?P<PID>.*?)</td>\s*)?(?:<td>(?P<Start>.*?)</td>\s*)?(?:<td>(?P<Runtime>.*?)</td>\s*)?
    (?:<td>(?P<Finish>.*?)</td>\s*)?(?:<td>(?P<Log>.*?)</td>\s*)?(?:<td>(?P<Items>.*?)</td>\s*)?
    [\w\W]*?</tr>""", re.X)
JOB_KEYS = ['project', 'spider', 'job', 'pid', 'start', 'runtime', 'finish', 'href_log', 'href_items']

_meta = {'unique_key_strings': {}, 'pageview': 1}


def _parse(text):
    text = re.sub(r'<thead>.*?</thead>', '', text, flags=re.S)
    return [dict(zip(JOB_KEYS, job)) for job in re.findall(JOB_PATTERN, text)]


def _handle_unique_constraint(jobs, node, flashes):
    seen = OrderedDict()
    for job in jobs:
        if job['finish']:
            break
        key = (job['project'], job['spider'], job['job'])
        if key in seen:
            start = seen[key]['start']
            finish = seen[key]['finish']
            uks = '/'.join(list(key) + [start, finish, str(node)])
            msg = ("Ignore seen running job: %s, started at %s" % ('/'.join(key), start) if start
                   else "Ignore seen pending job: %s" % ('/'.join(key)))
            if uks not in _meta['unique_key_strings']:
                _meta['unique_key_strings'][uks] = None
                flashes.append(('warning' if start else 'info', msg))
            seen.pop(key)
        seen[key] = job
    for job in reversed(jobs):
        if not job['finish']:
            break
        key = (job['project'], job['spider'], job['job'])
        if key in seen:
            uks = '/'.join(list(key) + [job['start'], job['finish'], str(node)])
            if uks not in _meta['unique_key_strings']:
                _meta['unique_key_strings'][uks] = None
                flashes.append(('info', "Ignore seen finished job: %s, started at %s" % ('/'.join(key), job['start'])))
        else:
            seen[key] = job
    return list(seen.values())


async def _db_insert(session, Job, jobs, liststats, flashes):
    records = []
    for job in jobs:
        record = (await session.execute(select(Job).filter_by(
            project=job['project'], spider=job['spider'], job=job['job']))).scalar_one_or_none()
        if record:
            if record.deleted == DELETED:
                if record.status == STATUS_FINISHED and str(record.start) == job['start']:
                    continue
                record.deleted = NOT_DELETED
                record.pages = None
                record.items = None
                flashes.append(('warning', "Recover deleted job: %s" % job))
        else:
            record = Job()
        records.append(record)
        for k, v in job.items():
            v = v or None
            if k in ['start', 'finish']:
                v = datetime.strptime(v, '%Y-%m-%d %H:%M:%S') if v else None
            elif k == 'pid':
                # parsed from scrapyd's HTML as a string; postgres rejects str->int binds
                v = int(v) if v else None
            elif k in ['href_log', 'href_items']:
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
            record.pages = None
            record.items = None
        elif liststats:
            try:
                data = liststats[job['project']][job['spider']][job['job']]
                record.pages = data['pages']
                record.items = data['items']
            except (KeyError, TypeError):
                pass
        record.update_time = datetime.now()
    session.add_all(records)
    await session.commit()


async def _db_clean_pending(session, Job, jobs_backup):
    current = [(j['project'], j['spider'], j['job']) for j in jobs_backup if not j['start']]
    rows = (await session.execute(select(Job).filter_by(start=None))).scalars().all()
    for record in rows:
        if (record.project, record.spider, record.job) not in current:
            await session.delete(record)
    await session.commit()
