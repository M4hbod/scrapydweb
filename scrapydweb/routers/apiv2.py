# coding: utf-8
"""JSON API for the React (shadcn) frontend.

Thin handlers under the /api prefix. Reads reuse the same building blocks as the
server-rendered routers (services/dashboard, jobs persist/query helpers, scrapyd
proxy); mutating actions reuse the existing JSON endpoints (tasks.xhr, scrapyd api)
until the legacy UI is removed at cutover.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from ..context import NodeContext, get_node_context
from ..db import Pagination, SessionLocal, get_metadata
from ..models import Task, TaskJobResult, TaskResult
from ..scheduler import STATE_RUNNING, scheduler
from ..services.dashboard import build_cluster_dashboard, search_jobs
from ..urls import safe_url_for as u

router = APIRouter(prefix='/api')

NA = 'N/A'


def _dt(value):
    return str(value)[:19] if value else None


def _server_list(settings):
    servers = settings.get('SCRAPYD_SERVERS', []) or []
    groups = settings.get('SCRAPYD_SERVERS_GROUPS', []) or []
    publics = settings.get('SCRAPYD_SERVERS_PUBLIC_URLS', None) or [''] * len(servers)
    out = []
    for idx, server in enumerate(servers):
        out.append(dict(
            node=idx + 1,
            server=server,
            group=groups[idx] if idx < len(groups) else '',
            public_url=publics[idx] if idx < len(publics) else '',
        ))
    return out


# ------------------------------------------------------------------ cluster
@router.get('/nodes', name='api.nodes')
async def api_nodes(request: Request):
    settings = request.app.state.settings
    return JSONResponse({'nodes': _server_list(settings)})


@router.get('/dashboard', name='api.dashboard')
async def api_dashboard(request: Request):
    # DB/aggregate only: must work with zero servers configured (setup state)
    dashboard = await build_cluster_dashboard(request.app)
    return JSONResponse({'dashboard': dashboard, 'nodes': _server_list(request.app.state.settings)})


@router.get('/{node:int}/search/', name='api.search')
async def api_search(request: Request, node: int, q: str = ''):
    return JSONResponse({'results': await search_jobs(request.app, q)})


@router.get('/metadata', name='api.metadata')
async def api_metadata():
    meta = await get_metadata()
    meta.pop('password', None)
    return JSONResponse({'metadata': {k: (str(v) if isinstance(v, datetime) else v) for k, v in meta.items()}})


# ------------------------------------------------------------------ jobs
@router.api_route('/{node:int}/jobs/', methods=['GET', 'POST'], name='api.jobs')
async def api_jobs(request: Request, node: int, page: int = 1, per_page: int = 100,
                   ctx: NodeContext = Depends(get_node_context)):
    """Live jobs of one node: fetch from scrapyd, persist, return the DB view as JSON."""
    from . import jobs as jobs_mod

    page = max(1, page)
    per_page = max(1, min(per_page, 1000))

    import asyncio

    app = request.app
    url = 'http://%s/jobs' % ctx.SCRAPYD_SERVER
    client = app.state.http_client
    from ..services.scrapyd import request_scrapyd

    # job stats from the central collector (job_stats table) -- same nested
    # shape the old logparser stats.json had: datas[project][spider][job]
    async def _fetch_liststats():
        from ..models import JobStats
        datas = {}
        try:
            async with SessionLocal() as s:
                stats_rows = (await s.execute(select(JobStats).filter_by(
                    server=ctx.SCRAPYD_SERVER))).scalars().all()
            for r in stats_rows:
                datas.setdefault(r.project, {}).setdefault(r.spider, {})[r.job] = dict(
                    pages=r.pages, items=r.items, runtime=r.runtime,
                    finish_reason=r.finish_reason, latest_log_time=r.latest_log_time)
        except Exception:
            pass
        return datas

    from ..services.job_versions import versions_for_server
    (status_code, text), liststats, job_versions = await asyncio.gather(
        request_scrapyd(client, url, auth=ctx.AUTH, as_json=False), _fetch_liststats(),
        versions_for_server(ctx.SCRAPYD_SERVER))
    import re as _re
    if status_code != 200 or not _re.search(r'<h1>Jobs</h1>', text):
        return JSONResponse({'status': 'error', 'status_code': status_code,
                             'message': 'Fail to request scrapyd /jobs', 'url': url}, status_code=200)

    parsed = jobs_mod._parse(text)
    jobs_backup = list(parsed)
    flashes = []

    try:
        unique_jobs = jobs_mod._handle_unique_constraint(parsed, node, flashes)
        from ..db import get_jobs_table
        Job = await get_jobs_table(node, ctx.SCRAPYD_SERVER)
        async with SessionLocal() as session:
            await jobs_mod._db_insert(session, Job, unique_jobs, liststats, flashes)
            await jobs_mod._db_clean_pending(session, Job, jobs_backup)
            # finalize stale RUNNING rows: the fetch succeeded, so any running job
            # absent from scrapyd's list is no longer running (scrapyd restart /
            # finished while we were not looking). Take finish data from logparser.
            current = {(j['project'], j['spider'], j['job']) for j in jobs_backup}
            stale = (await session.execute(
                select(Job).filter_by(deleted='0', status='1'))).scalars().all()
            finalized = False
            for r in stale:
                if (r.project, r.spider, r.job) in current:
                    continue
                r.status, r.pid, finalized = '2', None, True
                try:
                    data = liststats[r.project][r.spider][r.job]
                    r.pages, r.items = data['pages'], data['items']
                    r.runtime = data.get('runtime') or r.runtime
                    lt = data.get('latest_log_time')
                    if lt:
                        r.finish = datetime.strptime(lt, '%Y-%m-%d %H:%M:%S')
                except (KeyError, TypeError, ValueError):
                    pass
                if r.finish is None:
                    r.finish = r.update_time  # best effort: last time we saw it
            if finalized:
                await session.commit()
            # raw query (no display decoration -- the legacy _query mutates rows for Jinja)
            total = (await session.execute(select(func.count()).select_from(Job)
                     .filter_by(deleted='0'))).scalar() or 0
            # pending/running first, then by execution start time (newest first)
            db_rows = (await session.execute(
                select(Job).filter_by(deleted='0')
                .order_by(Job.status.asc(), Job.start.desc().nullslast(), Job.id.desc())
                .limit(per_page).offset((page - 1) * per_page))).scalars().all()
            # backfill pages/items for rows scrapyd no longer lists (e.g. after a
            # scrapyd restart) as long as logparser's stats.json still has them
            if liststats:
                dirty = False
                for j in db_rows:
                    if j.pages is None and j.start is not None:
                        try:
                            data = liststats[j.project][j.spider][j.job]
                            j.pages, j.items = data['pages'], data['items']
                            dirty = True
                        except (KeyError, TypeError):
                            pass
                if dirty:
                    await session.commit()
    except Exception as err:
        return JSONResponse({'status': 'error', 'message': 'Fail to persist jobs: %s' % err}, status_code=200)

    app_ = request.app
    rows = []
    for j in db_rows:
        try:
            finish_reason = liststats[j.project][j.spider][j.job].get('finish_reason')
        except (KeyError, TypeError):
            finish_reason = None
        rows.append(dict(
            id=j.id, project=j.project, spider=j.spider, job=j.job,
            status=j.status, pid=j.pid, pages=j.pages, items=j.items,
            version=job_versions.get((j.project, j.job)),
            finish_reason=finish_reason,
            start=_dt(j.start), finish=_dt(j.finish), runtime=j.runtime,
            update_time=_dt(j.update_time),
            href_log=j.href_log, href_items=j.href_items,
            url_stats=u(app_, 'log', node=node, opt='stats', project=j.project, spider=j.spider, job=j.job),
            url_log=u(app_, 'log', node=node, opt='utf8', project=j.project, spider=j.spider, job=j.job),
            url_stop=u(app_, 'api', node=node, opt='stop', project=j.project, version_spider_job=j.job),
            url_start=u(app_, 'api', node=node, opt='start', project=j.project, version_spider_job=j.spider),
        ))
    pages_total = max(1, (total + per_page - 1) // per_page) if per_page else 1
    return JSONResponse({'status': 'ok', 'node': node, 'page': page, 'per_page': per_page,
                         'pages': pages_total, 'total': total, 'jobs': rows,
                         'warnings': [m for _c, m in flashes]})


# ------------------------------------------------------------------ deploy
@router.get('/{node:int}/deploy/folders/', name='api.deploy_folders')
async def api_deploy_folders(request: Request, node: int,
                             ctx: NodeContext = Depends(get_node_context)):
    """Deployable scrapy projects found in SCRAPY_PROJECTS_DIR."""
    from .deploy import scan_projects_dir
    scan = scan_projects_dir(request.app)
    return JSONResponse(dict(
        status='ok',
        projects_dir=scan['projects_dir'].replace('\\', '/'),
        latest_folder=scan['latest_folder'],
        folders=[dict(folder=f, project=p, modified=m)
                 for f, p, m in zip(scan['folders'], scan['projects'], scan['modification_times'])],
    ))


# ------------------------------------------------------------------ code viewer (deployed eggs)
def _egg_path(project, version):
    import re as _r
    from ..vars import DEPLOY_PATH, LEGAL_NAME_PATTERN, STRICT_NAME_PATTERN
    import os as _o
    p = _r.sub(STRICT_NAME_PATTERN, '_', project or '')
    v = _r.sub(LEGAL_NAME_PATTERN, '-', version or '')
    return _o.path.join(DEPLOY_PATH, '%s_%s.egg' % (p, v))


@router.get('/code/{project}/{version}/', name='api.code_list')
async def api_code_list(project: str, version: str):
    """List source files inside the deployed egg for (project, version)."""
    import os as _o
    import zipfile
    path = _egg_path(project, version)
    if not _o.path.isfile(path):
        return JSONResponse({'status': 'error',
                             'message': 'egg not found -- this version was probably '
                                        'deployed outside scrapydweb'}, status_code=404)
    try:
        with zipfile.ZipFile(path) as zf:
            files = [dict(path=i.filename, size=i.file_size)
                     for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        return JSONResponse({'status': 'error', 'message': 'corrupt egg file'}, status_code=500)
    files.sort(key=lambda f: f['path'])
    return JSONResponse({'status': 'ok', 'project': project, 'version': version, 'files': files})


@router.get('/code/{project}/{version}/file', name='api.code_file')
async def api_code_file(project: str, version: str, path: str = ''):
    import os as _o
    import zipfile
    egg = _egg_path(project, version)
    if not _o.path.isfile(egg):
        return JSONResponse({'status': 'error', 'message': 'egg not found'}, status_code=404)
    with zipfile.ZipFile(egg) as zf:
        if path not in zf.namelist():  # membership check = zip-slip safe
            return JSONResponse({'status': 'error', 'message': 'no such file in egg'},
                                status_code=404)
        data = zf.read(path)
    if len(data) > 512 * 1024:
        return JSONResponse({'status': 'error', 'message': 'file too large to display'})
    if b'\x00' in data:
        return JSONResponse({'status': 'error', 'message': 'binary file'})
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return JSONResponse({'status': 'error', 'message': 'binary file'})
    return JSONResponse({'status': 'ok', 'path': path, 'text': text})


# ------------------------------------------------------------------ download proxy
import re as _seg_re
_SEGMENT_OK = _seg_re.compile(r'^[A-Za-z0-9 ._\-]+$')


@router.get('/{node:int}/download/{kind}/{project}/{spider}/{filename}', name='api.download')
async def api_download(request: Request, node: int, kind: str, project: str, spider: str,
                       filename: str, ctx: NodeContext = Depends(get_node_context)):
    """Stream a log/items file from scrapyd with server-side auth.

    Keeps scrapyd credentials out of the browser (no basic-auth popups).
    """
    import base64
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse

    if kind not in ('logs', 'items') or not all(
            _SEGMENT_OK.match(seg) and seg not in ('.', '..')
            for seg in (project, spider, filename)):
        return JSONResponse({'status': 'error', 'message': 'invalid path'}, status_code=400)

    url = 'http://%s/%s/%s/%s/%s' % (ctx.SCRAPYD_SERVER, kind,
                                     quote(project), quote(spider), quote(filename))
    client = request.app.state.http_client
    req = client.build_request('GET', url, headers={'accept-encoding': 'identity'})
    if ctx.AUTH:
        req.headers['Authorization'] = 'Basic ' + base64.b64encode(
            ('%s:%s' % tuple(ctx.AUTH)).encode()).decode()
    upstream = await client.send(req, stream=True)
    if upstream.status_code != 200:
        await upstream.aclose()
        return JSONResponse({'status': 'error', 'status_code': upstream.status_code,
                             'message': 'scrapyd returned %s' % upstream.status_code},
                            status_code=404)

    async def body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body(),
        media_type=upstream.headers.get('content-type', 'application/octet-stream'),
        headers={'Content-Disposition': 'attachment; filename="%s"' % filename},
    )


# ------------------------------------------------------------------ log
@router.get('/{node:int}/log/{opt}/{project}/{spider}/{job}/', name='api.log')
async def api_log(request: Request, node: int, opt: str, project: str, spider: str, job: str,
                  ctx: NodeContext = Depends(get_node_context)):
    """Log text (opt=utf8) or logparser stats (opt=stats) as JSON."""
    from .log import LogHandler
    return await LogHandler(request, node, ctx, opt, project, spider, job, as_json=True).run()


# ------------------------------------------------------------------ cron preview
@router.post('/cron/preview', name='api.cron_preview')
async def api_cron_preview(request: Request):
    """Next fire times for a cron spec (same engine that runs the tasks)."""
    from apscheduler.triggers.cron import CronTrigger
    form = await request.form()
    kwargs = {k: (form.get(k) or d) for k, d in
              [('year', '*'), ('month', '*'), ('day', '*'), ('week', '*'),
               ('day_of_week', '*'), ('hour', '*'), ('minute', '0'), ('second', '0')]}
    tz = form.get('timezone') or None
    try:
        trigger = CronTrigger(timezone=tz, **kwargs)
    except Exception as err:
        return JSONResponse({'status': 'error', 'message': str(err)})
    now = datetime.now(trigger.timezone)
    fires, prev = [], None
    for _ in range(5):
        nxt = trigger.get_next_fire_time(prev, prev or now)
        if not nxt:
            break
        fires.append(str(nxt)[:19])
        prev = nxt
    return JSONResponse({'status': 'ok', 'next_runs': fires,
                         'timezone': str(trigger.timezone)})


# ------------------------------------------------------------------ tasks
@router.get('/{node:int}/tasks/', name='api.tasks')
async def api_tasks(request: Request, node: int, page: int = 1, per_page: int = 100):
    from ..db import create_all_for_bind
    await create_all_for_bind(None)
    out = []
    async with SessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(Task))).scalar()
        rows = (await session.execute(select(Task).order_by(Task.id.desc())
                .limit(per_page).offset((page - 1) * per_page))).scalars().all()
        for task in rows:
            trs = (await session.execute(select(TaskResult).filter_by(task_id=task.id)
                   .order_by(TaskResult.id.desc()))).scalars().all()
            run_times = len(trs)
            fail_times = sum(1 for t in trs if t.fail_count > 0)
            if trs:
                latest = trs[0]
                prev_run_result = ('PASS' if latest.fail_count == 0 and latest.pass_count >= 1
                                   else 'FAIL %s, PASS %s' % (latest.fail_count, latest.pass_count))
            else:
                prev_run_result = NA
            job = scheduler.get_job(str(task.id))
            if job:
                status = 'Running' if job.next_run_time else 'Paused'
                next_run_time = str(job.next_run_time) if job.next_run_time else None
            else:
                status = 'Finished'
                next_run_time = None
            out.append(dict(
                id=task.id, name=task.name or '', project=task.project, version=task.version,
                spider=task.spider, jobid=task.jobid, trigger=task.trigger,
                create_time=_dt(task.create_time), update_time=_dt(task.update_time),
                year=task.year, month=task.month, day=task.day, week=task.week,
                day_of_week=task.day_of_week, hour=task.hour, minute=task.minute, second=task.second,
                start_date=task.start_date, end_date=task.end_date, timezone=task.timezone,
                settings_arguments=task.settings_arguments, selected_nodes=task.selected_nodes,
                status=status, next_run_time=next_run_time,
                run_times=run_times, fail_times=fail_times, prev_run_result=prev_run_result,
            ))
    return JSONResponse({'status': 'ok', 'page': page, 'per_page': per_page,
                         'total': total or 0, 'tasks': out,
                         'scheduler_enabled': scheduler.state == STATE_RUNNING})


@router.get('/{node:int}/tasks/{task_id:int}/results/', name='api.task_results')
async def api_task_results(request: Request, node: int, task_id: int, page: int = 1, per_page: int = 100):
    async with SessionLocal() as session:
        task = (await session.execute(select(Task).filter_by(id=task_id))).scalar_one_or_none()
        if task is None:
            return JSONResponse({'status': 'error', 'message': 'task #%s not found' % task_id}, status_code=404)
        total = (await session.execute(
            select(func.count()).select_from(TaskResult).filter_by(task_id=task_id))).scalar()
        trs = (await session.execute(select(TaskResult).filter_by(task_id=task_id)
               .order_by(TaskResult.id.desc()).limit(per_page).offset((page - 1) * per_page))).scalars().all()
        results = []
        for tr in trs:
            tjrs = (await session.execute(select(TaskJobResult).filter_by(task_result_id=tr.id)
                    .order_by(TaskJobResult.id.desc()))).scalars().all()
            results.append(dict(
                id=tr.id, execute_time=_dt(tr.execute_time),
                fail_count=tr.fail_count, pass_count=tr.pass_count,
                job_results=[dict(id=r.id, node=r.node, server=r.server, status_code=r.status_code,
                                  status=r.status, result=r.result, run_time=_dt(r.run_time))
                             for r in tjrs],
            ))
    return JSONResponse({'status': 'ok', 'task': dict(id=task.id, name=task.name or '', project=task.project,
                                                      spider=task.spider, jobid=task.jobid),
                         'page': page, 'per_page': per_page, 'total': total or 0, 'results': results})
