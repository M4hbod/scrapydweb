# coding: utf-8
"""Jobs dashboard (ports views/dashboard/jobs.py) - async SQLAlchemy 2.0."""
from collections import OrderedDict
from datetime import datetime
import re
import traceback
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from ..common import json_dumps
from ..context import NodeContext, compute_features, get_node_context, DEFAULT_LATEST_VERSION
from ..db import Pagination, SessionLocal, get_jobs_table, get_metadata, jobs_table_for, set_metadata
from ..scheduler import safe_get_jobs, scheduler
from ..services.scrapyd import OK, request_scrapyd
from ..templating import render
from ..urls import safe_url_for as u

router = APIRouter()

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


async def _query(session, Job, node, ctx, page, per_page, jobs_backup, public_url, url):
    current_pids = [int(j['pid']) for j in jobs_backup if j['pid']]
    total = (await session.execute(
        select(func.count()).select_from(Job).filter_by(deleted=NOT_DELETED))).scalar()
    stmt = (select(Job).filter_by(deleted=NOT_DELETED)
            .order_by(Job.status.asc(), Job.finish.desc(), Job.start.asc(), Job.id.asc())
            .limit(per_page).offset((page - 1) * per_page))
    rows = (await session.execute(stmt)).scalars().all()
    app = ctx  # not used; placeholder
    for index, job in enumerate(rows, (page - 1) * per_page + 1):
        job.index = index
        job.pid = job.pid or ''
        job.start = job.start or ''
        job.runtime = job.runtime or ''
        job.finish = job.finish or ''
        job.update_time = str(job.update_time)[:19]
        job.to_be_killed = bool(job.pid and job.pid not in current_pids)
        _app = _query.app
        if job.finish:
            job.url_multinode = u(_app, 'servers', node=node, opt='schedule', project=job.project,
                                  version_job=DEFAULT_LATEST_VERSION, spider=job.spider)
            job.url_action = u(_app, 'schedule', node=node, project=job.project,
                               version=DEFAULT_LATEST_VERSION, spider=job.spider)
        else:
            job.url_multinode = u(_app, 'servers', node=node, opt='stop', project=job.project, version_job=job.job)
            job.url_action = u(_app, 'api', node=node, opt='stop', project=job.project, version_spider_job=job.job)
        if job.start:
            job.pages = NA if job.pages is None else job.pages
            job.items = NA if job.items is None else job.items
        else:
            job.pages = None
            job.items = None
            continue
        jf = 'True' if job.finish else None
        job.url_utf8 = u(_app, 'log', node=node, opt='utf8', project=job.project, ui=ctx.UI,
                         spider=job.spider, job=job.job, job_finished=jf)
        job.url_stats = u(_app, 'log', node=node, opt='stats', project=job.project, ui=ctx.UI,
                          spider=job.spider, job=job.job, job_finished=jf)
        job.url_clusterreports = u(_app, 'clusterreports', node=node, project=job.project,
                                   spider=job.spider, job=job.job)
        job.url_source = urljoin(public_url or url, job.href_log)
        job.url_items = urljoin(public_url or url, job.href_items) if job.href_items else ''
        job.url_delete = u(_app, 'jobs.xhr', node=node, action='delete', id=job.id)
    return Pagination(rows, page, per_page, total)


async def jobs(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    _query.app = app
    settings = app.state.settings
    qp = request.query_params
    meta = await get_metadata()

    style = qp.get('style')
    style = style if style in ['database', 'classic'] else meta.get('jobs_style', 'database')
    if style != meta.get('jobs_style'):
        await set_metadata('jobs_style', style)
    per_page = int(qp.get('per_page', meta.get('jobs_per_page', 100)))
    if per_page != meta.get('jobs_per_page'):
        await set_metadata('jobs_per_page', per_page)
    page = int(qp.get('page', 1))

    url = 'http://%s/jobs' % ctx.SCRAPYD_SERVER
    public_url = ''
    is_post = request.method == 'POST'
    use_mobileui = ctx.USE_MOBILEUI
    if use_mobileui:
        style = 'classic'
        template = 'scrapydweb/jobs_mobileui.html'
    elif style == 'classic':
        template = 'scrapydweb/jobs_classic.html'
    else:
        template = 'scrapydweb/jobs.html'

    client = app.state.http_client
    status_code, text = await request_scrapyd(client, url, auth=ctx.AUTH, as_json=False)
    if status_code != 200 or not re.search(r'<h1>Jobs</h1>', text):
        fail = 'scrapydweb/fail_mobileui.html' if use_mobileui else 'scrapydweb/fail.html'
        page_ctx = dict(node=node, url=url, status_code=status_code, text=text,
                        tip="Click the above link to make sure your Scrapyd server is accessable. ")
        return render(request, fail, node, ctx, page=page_ctx)

    parsed = _parse(text)
    jobs_backup = list(parsed)
    if qp.get('listjobs'):
        return JSONResponse(parsed)

    flashes = []
    liststats = {}
    if is_post:
        st, js = await request_scrapyd(client, 'http://%s/logs/stats.json' % ctx.SCRAPYD_SERVER,
                                       auth=ctx.AUTH, as_json=True)
        if js.get('status') == OK:
            liststats = js.get('datas', {})
    else:
        _meta['pageview'] += 1

    pagination = None
    if style == 'database' or is_post:
        try:
            if qp.get('raise_exception') == 'True':
                assert False, "raise_exception: True"
            unique_jobs = _handle_unique_constraint(parsed, node, flashes)
            Job = await get_jobs_table(node, ctx.SCRAPYD_SERVER)
            async with SessionLocal() as session:
                await _db_insert(session, Job, unique_jobs, liststats, flashes)
                await _db_clean_pending(session, Job, jobs_backup)
                pagination = await _query(session, Job, node, ctx, page, per_page,
                                          jobs_backup, public_url, url)
        except Exception as err:
            flashes.append(('warning', "Fail to persist jobs in database: %s" % err))
            if style == 'database' and not is_post:
                style = 'classic'
                template = 'scrapydweb/jobs_classic.html'
                await set_metadata('jobs_style', style)

    if is_post:
        jobs_dict = {}
        if pagination:
            for job in pagination.items:
                key = '%s/%s/%s' % (job.project, job.spider, job.job)
                value = {k: v for k, v in job.__dict__.items() if not k.startswith('_')}
                for k in ['create_time', 'update_time', 'start', 'finish']:
                    if k in value:
                        value[k] = str(value[k])
                jobs_dict[key] = value
        return JSONResponse(jobs_dict)

    pending, running, finished = [], [], []
    if style != 'database':
        pending, running, finished = _handle_without_db(jobs_backup, node, ctx)

    any_jobs = any(j.next_run_time for j in safe_get_jobs('default'))
    FEATURES = compute_features(settings, ctx, meta.get('jobs_style'), any_jobs, scheduler.state)
    page_ctx = dict(
        node=node, url=url,
        url_schedule=u(app, 'schedule', node=node),
        url_liststats=u(app, 'api', node=node, opt='liststats'),
        url_liststats_source='http://%s/logs/stats.json' % ctx.SCRAPYD_SERVER,
        SCRAPYD_SERVER=ctx.SCRAPYD_SERVER.split(':')[0],
        LOGPARSER_VERSION=__import__('logparser').__version__,
        JOBS_RELOAD_INTERVAL=settings.get('JOBS_RELOAD_INTERVAL', 300),
        IS_IE_EDGE=ctx.IS_IE_EDGE, pageview=_meta['pageview'], FEATURES=FEATURES,
    )
    if style == 'database':
        page_ctx.update(url_jobs_classic=u(app, 'jobs', node=node, style='classic'), jobs=pagination)
    else:
        finished.sort(key=lambda x: (x['finish'], x['start']), reverse=True)
        limit = settings.get('JOBS_FINISHED_JOBS_LIMIT', 0)
        if limit > 0:
            finished = finished[:limit]
        page_ctx.update(colspan=14, url_jobs_database=u(app, 'jobs', node=node, style='database'),
                        pending_jobs=pending, running_jobs=running, finished_jobs=finished,
                        SHOW_JOBS_JOB_COLUMN=settings.get('SHOW_JOBS_JOB_COLUMN', False))
    return render(request, template, node, ctx, page=page_ctx, flashes=flashes)


def _handle_without_db(jobs_list, node, ctx):
    from .. import urls
    app = _query.app
    pending, running, finished = [], [], []
    for job in jobs_list:
        job['start'] = job['start'][5:]
        job['finish'] = job['finish'][5:]
        if not job['start']:
            pending.append(job)
        else:
            if job['finish']:
                finished.append(job)
                job['url_multinode_run'] = u(app, 'servers', node=node, opt='schedule', project=job['project'],
                                             version_job=DEFAULT_LATEST_VERSION, spider=job['spider'])
                job['url_schedule'] = u(app, 'schedule', node=node, project=job['project'],
                                        version=DEFAULT_LATEST_VERSION, spider=job['spider'])
                job['url_start'] = u(app, 'api', node=node, opt='start', project=job['project'],
                                     version_spider_job=job['spider'])
            else:
                running.append(job)
                job['url_forcestop'] = u(app, 'api', node=node, opt='forcestop', project=job['project'],
                                         version_spider_job=job['job'])
            jf = 'True' if job['finish'] else None
            job['url_utf8'] = u(app, 'log', node=node, opt='utf8', project=job['project'], ui=ctx.UI,
                                spider=job['spider'], job=job['job'], job_finished=jf)
            job['url_stats'] = u(app, 'log', node=node, opt='stats', project=job['project'], ui=ctx.UI,
                                 spider=job['spider'], job=job['job'], job_finished=jf)
            job['url_clusterreports'] = u(app, 'clusterreports', node=node, project=job['project'],
                                          spider=job['spider'], job=job['job'])
            m = re.search(HREF_PATTERN, job['href_items'])
            job['url_items'] = urljoin(job.get('public_url', '') or ('http://%s/jobs' % ctx.SCRAPYD_SERVER),
                                       m.group(1)) if m else ''
        if not job['finish']:
            job['url_multinode_stop'] = u(app, 'servers', node=node, opt='stop', project=job['project'],
                                          version_job=job['job'])
            job['url_stop'] = u(app, 'api', node=node, opt='stop', project=job['project'],
                                version_spider_job=job['job'])
    return pending, running, finished


async def jobs_xhr(request: Request, node: int, action: str, id: int,
                   ctx: NodeContext = Depends(get_node_context)):
    Job = jobs_table_for(node) or await get_jobs_table(node, ctx.SCRAPYD_SERVER)
    js = {}
    async with SessionLocal() as session:
        job = (await session.execute(select(Job).filter_by(id=id))).scalar_one_or_none()
        if job:
            try:
                job.deleted = DELETED
                await session.commit()
            except Exception as err:
                await session.rollback()
                js = dict(status='error', message=str(err))
            else:
                js = dict(status=OK, tip="Deleted %s" % id)
        else:
            js = dict(status='error', message="job #%s not found in the database" % id)
    return JSONResponse(js)


router.add_api_route('/{node:int}/jobs/', jobs, methods=['GET', 'POST'], name='jobs')
router.add_api_route('/{node:int}/jobs/xhr/{action}/{id:int}/', jobs_xhr,
                     methods=['GET', 'POST'], name='jobs.xhr')
