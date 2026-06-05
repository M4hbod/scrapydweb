# coding: utf-8
"""Timer Tasks pages + xhr (ports views/overview/tasks.py)."""
from datetime import datetime, timedelta
import json
import logging
import traceback

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import and_, func, select

from ..context import NodeContext, get_node_context
from ..db import Pagination, SessionLocal, get_metadata, set_metadata
from ..models import Task, TaskJobResult, TaskResult
from ..scheduler import STATE_PAUSED, STATE_RUNNING, safe_get_jobs, scheduler
from ..templating import render
from ..urls import safe_url_for as u
from ..vars import SCHEDULER_STATE_DICT, TIMER_TASKS_HISTORY_LOG

router = APIRouter()
apscheduler_logger = logging.getLogger('apscheduler')
OK, ERROR, NA = 'ok', 'error', 'N/A'


def _rm_micro(dt):
    return str(dt)[:19]


@router.get('/tasks/history/', name='tasks.history')
async def history():
    return FileResponse(TIMER_TASKS_HISTORY_LOG, media_type='text/plain')


def _fail(ctx):
    return 'scrapydweb/fail_mobileui.html' if ctx.USE_MOBILEUI else 'scrapydweb/fail.html'


async def _paginate(session, stmt_count, stmt_items, page, per_page):
    total = (await session.execute(stmt_count)).scalar()
    rows = (await session.execute(stmt_items.limit(per_page).offset((page - 1) * per_page))).scalars().all()
    return rows, total


async def tasks_view(request: Request, node: int, task_id: int = None, task_result_id: int = None,
                     ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    qp = request.query_params
    flashes = []
    flash = qp.get('flash', '')
    if flash:
        flashes.append(('info', flash))
    meta = await get_metadata()
    per_page = int(qp.get('per_page', meta.get('tasks_per_page', 100)))
    if per_page != meta.get('tasks_per_page'):
        await set_metadata('tasks_per_page', per_page)
    page = int(qp.get('page', 1))

    async with SessionLocal() as session:
        task = None
        if task_id:
            task = (await session.execute(select(Task).filter_by(id=task_id))).scalar_one_or_none()
            if not task:
                return render(request, _fail(ctx), node, ctx, page=dict(node=node, message="Task #%s not found" % task_id))

        if task_id and task_result_id:
            return await _task_job_results(request, node, ctx, session, task, task_id, task_result_id, page, per_page)
        if task_id:
            return await _task_results(request, node, ctx, session, task, task_id, page, per_page)
        return await _tasks_list(request, node, ctx, session, page, per_page, flashes)


async def _tasks_list(request, node, ctx, session, page, per_page, flashes):
    app = request.app
    if scheduler.state == STATE_PAUSED:
        flashes.append(('warning', "Click the DISABLED button to enable the scheduler for timer tasks. "))
    # remove apscheduler jobs without task
    all_tasks = (await session.execute(select(Task))).scalars().all()
    task_id_set = set(str(t.id) for t in all_tasks)
    for j in safe_get_jobs('default'):
        if j.id not in task_id_set:
            try:
                scheduler.remove_job(j.id, jobstore='default')
                flashes.append(('warning', "apscheduler_job #%s removed since task #%s not exist. " % (j.id, j.id)))
            except Exception:
                pass

    total = (await session.execute(select(func.count()).select_from(Task))).scalar()
    rows = (await session.execute(select(Task).order_by(Task.id.desc())
            .limit(per_page).offset((page - 1) * per_page))).scalars().all()
    for index, task in enumerate(rows, (page - 1) * per_page + 1):
        task.index = index
        task.name = task.name or ''
        task.timezone = task.timezone or str(scheduler.timezone)
        task.create_time = _rm_micro(task.create_time)
        task.update_time = _rm_micro(task.update_time)
        trs = (await session.execute(select(TaskResult).filter_by(task_id=task.id)
               .order_by(TaskResult.id.desc()))).scalars().all()
        task.run_times = len(trs)
        task.url_task_results = u(app, 'tasks', node=node, task_id=task.id)
        if trs:
            task.fail_times = sum(1 for t in trs if t.fail_count > 0)
            latest = trs[0]
            if latest.fail_count == 0 and latest.pass_count == 1:
                tjr = (await session.execute(select(TaskJobResult).filter_by(task_result_id=latest.id)
                       .order_by(TaskJobResult.id.desc()))).scalars().first()
                task.prev_run_result = tjr.result[-19:]
                task.url_prev_run_result = u(app, 'log', node=tjr.node, opt='stats', project=task.project,
                                             spider=task.spider, job=tjr.result)
            else:
                task.prev_run_result = 'FAIL %s, PASS %s' % (latest.fail_count, latest.pass_count)
                task.url_prev_run_result = u(app, 'tasks', node=node, task_id=task.id, task_result_id=latest.id)
        else:
            task.fail_times = 0
            task.prev_run_result = NA
            task.url_prev_run_result = task.url_task_results
        task.url_edit = u(app, 'schedule', node=node, task_id=task.id)
        job = scheduler.get_job(str(task.id))
        if job:
            if job.next_run_time:
                task.status = 'Running'
                task.next_run_time = ("Click DISABLED button first. " if scheduler.state == STATE_PAUSED
                                      else str(job.next_run_time))
                task.url_fire = u(app, 'tasks.xhr', node=node, action='fire', task_id=task.id)
                action = 'pause'
            else:
                task.status = 'Paused'
                task.next_run_time = NA
                task.url_fire = ''
                action = 'resume'
            task.url_status = u(app, 'tasks.xhr', node=node, action=action, task_id=task.id)
            task.action = 'Stop'
            task.url_action = u(app, 'tasks.xhr', node=node, action='remove', task_id=task.id)
        else:
            task.status = 'Finished'
            task.url_status = task.url_task_results
            task.action = 'Delete'
            task.url_action = u(app, 'tasks.xhr', node=node, action='delete', task_id=task.id)
            task.next_run_time = NA
            task.url_fire = ''
    rows.sort(key=lambda t: t.status, reverse=True)
    tasks = Pagination(rows, page, per_page, total)

    if scheduler.state == STATE_RUNNING:
        scheduler_action_button = 'ENABLED'
        url_scheduler_action = u(app, 'tasks.xhr', node=node, action='disable')
    else:
        scheduler_action_button = 'DISABLED'
        url_scheduler_action = u(app, 'tasks.xhr', node=node, action='enable')
    page_ctx = dict(node=node, tasks=tasks, url_add_task=u(app, 'schedule', node=node, add_task='True'),
                    scheduler_action_button=scheduler_action_button, url_scheduler_action=url_scheduler_action,
                    url_tasks_history=u(app, 'tasks.history'))
    return render(request, 'scrapydweb/tasks.html', node, ctx, page=page_ctx, flashes=flashes)


async def _task_results(request, node, ctx, session, task, task_id, page, per_page):
    app = request.app
    total = (await session.execute(select(func.count()).select_from(TaskResult).filter_by(task_id=task_id))).scalar()
    rows = (await session.execute(select(TaskResult).filter_by(task_id=task_id).order_by(TaskResult.id.desc())
            .limit(per_page).offset((page - 1) * per_page))).scalars().all()
    with_job = bool(rows) and all((tr.fail_count + tr.pass_count) == 1 for tr in rows)
    template = 'scrapydweb/task_results_with_job.html' if with_job else 'scrapydweb/task_results.html'
    for index, tr in enumerate(rows, (page - 1) * per_page + 1):
        tr.index = index
        if with_job:
            tjr = (await session.execute(select(TaskJobResult).filter_by(task_result_id=tr.id)
                   .order_by(TaskJobResult.id.desc()))).scalars().first()
            tr.task_job_result_id = tjr.id
            tr.run_time = _rm_micro(tjr.run_time)
            tr.node = tjr.node
            tr.server = tjr.server
            tr.status_code = tjr.status_code
            tr.status = tjr.status
            tr.result = tjr.result
            tr.url_stats = (u(app, 'log', node=tjr.node, opt='stats', project=task.project,
                              spider=task.spider, job=tjr.result) if tjr.status == OK else '')
        else:
            tr.execute_time = _rm_micro(tr.execute_time)
            tr.url_task_job_results = u(app, 'tasks', node=node, task_id=task_id, task_result_id=tr.id)
        tr.url_action = u(app, 'tasks.xhr', node=node, action='delete', task_id=task_id, task_result_id=tr.id)
    task_results = Pagination(rows, page, per_page, total)
    page_ctx = dict(node=node, task_id=task_id, task=task, task_results=task_results,
                    url_tasks=u(app, 'tasks', node=node))
    return render(request, template, node, ctx, page=page_ctx)


async def _task_job_results(request, node, ctx, session, task, task_id, task_result_id, page, per_page):
    app = request.app
    total = (await session.execute(select(func.count()).select_from(TaskJobResult)
             .filter_by(task_result_id=task_result_id))).scalar()
    rows = (await session.execute(select(TaskJobResult).filter_by(task_result_id=task_result_id)
            .order_by(TaskJobResult.node.asc()).limit(per_page).offset((page - 1) * per_page))).scalars().all()
    for index, tjr in enumerate(rows, (page - 1) * per_page + 1):
        tjr.index = index
        tjr.run_time = _rm_micro(tjr.run_time)
        if tjr.status == OK:
            tjr.url_stats = u(app, 'log', node=tjr.node, opt='stats', project=task.project,
                              spider=task.spider, job=tjr.result)
            tjr.url_clusterreports = u(app, 'clusterreports', node=node, project=task.project,
                                       spider=task.spider, job=tjr.result)
        else:
            tjr.url_stats = ''
            tjr.url_clusterreports = ''
    task_job_results = Pagination(rows, page, per_page, total)
    page_ctx = dict(node=node, task_id=task_id, task_result_id=task_result_id, task=task,
                    task_job_results=task_job_results, url_tasks=u(app, 'tasks', node=node),
                    url_task_results=u(app, 'tasks', node=node, task_id=task_id))
    return render(request, 'scrapydweb/task_job_results.html', node, ctx, page=page_ctx)


# ---------------------------------------------------------------- xhr
async def tasks_xhr(request: Request, node: int, action: str, task_id: int = None, task_result_id: int = None,
                    ctx: NodeContext = Depends(get_node_context)):
    js = dict(action=action, task_id=task_id, task_result_id=task_result_id, url=str(request.url))
    try:
        await _xhr_dispatch(request, node, action, task_id, task_result_id, js)
    except Exception as err:
        apscheduler_logger.error(traceback.format_exc())
        js['status'] = 'exception'
        js['message'] = str(err)
    else:
        js.setdefault('status', OK)
    return JSONResponse(js)


async def _xhr_dispatch(request, node, action, task_id, task_result_id, js):
    app = request.app
    job = scheduler.get_job(str(task_id)) if task_id else None
    if action in ['disable', 'enable']:
        if action == 'disable':
            scheduler.pause()
        else:
            scheduler.resume()
        await set_metadata('scheduler_state', scheduler.state)
        js['tip'] = "Scheduler after '%s': %s" % (action, SCHEDULER_STATE_DICT[scheduler.state])
        return
    if action == 'delete':
        async with SessionLocal() as session:
            if task_result_id:
                tr = (await session.execute(select(TaskResult).filter_by(id=task_result_id))).scalar_one_or_none()
                if tr:
                    await session.delete(tr)
                    await session.commit()
                    js['tip'] = "task_result #%s deleted. " % task_result_id
                else:
                    js['status'] = ERROR
                    js['message'] = "task_result #%s not found. " % task_result_id
            elif task_id:
                if request.query_params.get('ignore_apscheduler_job') == 'True':
                    js['tip'] = "Ignore apscheduler_job #%s. " % task_id
                elif job:
                    job.remove()
                    js['tip'] = "apscheduler_job #%s removed. " % task_id
                else:
                    js['tip'] = "apscheduler_job #%s not found. " % task_id
                task = (await session.execute(select(Task).filter_by(id=task_id))).scalar_one_or_none()
                if task:
                    await session.delete(task)
                    await session.commit()
                    apscheduler_logger.warning("Task #%s deleted. ", task_id)
                    js['tip'] = js.get('tip', '') + "Task #%s deleted. " % task_id
                else:
                    js['status'] = ERROR
                    js['message'] = js.pop('tip', '') + "Task #%s not found. " % task_id
            else:
                await _delete_outdated(app, session, js)
        return
    if action == 'dump':
        await _dump(node, task_id, job, js)
        return
    if action == 'fire':
        if not job:
            js['status'] = ERROR
            js['message'] = "apscheduler_job #%s not found. " % task_id
        elif not job.next_run_time:
            js['status'] = ERROR
            js['message'] = "apscheduler_job #%s is paused, resume it first. " % task_id
        else:
            job.modify(next_run_time=datetime.now())
            js['tip'] = "Reload this page several seconds later to check out the fire result. "
            js['url_jump'] = u(app, 'tasks', node=node, task_id=task_id)
        return
    if action == 'list':
        async with SessionLocal() as session:
            if task_id and task_result_id:
                recs = (await session.execute(select(TaskJobResult).filter_by(task_result_id=task_result_id))).scalars().all()
            elif task_id:
                recs = (await session.execute(select(TaskResult).filter_by(task_id=task_id))).scalars().all()
            else:
                recs = (await session.execute(select(Task))).scalars().all()
        js['ids'] = [r.id for r in recs]
        return
    # pause|resume|remove
    if not job:
        js['status'] = ERROR
        js['message'] = "apscheduler_job #%s not found. " % task_id
        return
    if action == 'pause':
        job.pause()
    elif action == 'resume':
        job.resume()
    else:
        job.remove()
    js['tip'] = u"apscheduler_job #{tid} after '{a}': {j}".format(tid=task_id, a=action, j=scheduler.get_job(str(task_id)))


async def _dump(node, task_id, job, js):
    async with SessionLocal() as session:
        task = (await session.execute(select(Task).filter_by(id=task_id))).scalar_one_or_none() if task_id else None
    if not task:
        js['status'] = ERROR
        if job:
            js['data'] = dict(apscheduler_job=task_id)
            js['message'] = "apscheduler_job #%s found. " % task_id
        else:
            js['data'] = None
            js['message'] = "apscheduler_job #%s not found. " % task_id
        js['message'] += "Task #%s not found. " % task_id
        return
    data = {k: v for k, v in vars(task).items() if not k.startswith('_')}
    data['settings_arguments'] = json.loads(data['settings_arguments'])
    data['selected_nodes'] = json.loads(data['selected_nodes'])
    data['create_time'] = str(data['create_time'])
    data['update_time'] = str(data['update_time'])
    js['data'] = data
    if not job:
        data['apscheduler_job'] = None
        js['tip'] = "apscheduler_job #{id} not found. Task #{id} found. ".format(id=task_id)
        return
    aj = dict(id=job.id, name=job.name, kwargs=job.kwargs, misfire_grace_time=job.misfire_grace_time,
              coalesce=job.coalesce, max_instances=job.max_instances,
              next_run_time=str(job.next_run_time) if job.next_run_time else None)
    aj['trigger'] = {f.name: str(f) for f in job.trigger.fields}
    sd = job.trigger.start_date
    aj['trigger'].update(dict(
        start_date=str(sd) if sd else None,
        end_date=str(job.trigger.end_date) if job.trigger.end_date else None,
        timezone=str(job.trigger.timezone) if job.trigger.timezone else None,
        jitter=job.trigger.jitter))
    data['apscheduler_job'] = aj
    js['tip'] = "apscheduler_job #{id} found. Task #{id} found. ".format(id=task_id)


async def _delete_outdated(app, session, js):
    limit = app.state.settings.get('KEEP_TASK_RESULT_LIMIT', 1000)
    days = app.state.settings.get('KEEP_TASK_RESULT_WITHIN_DAYS', 31)
    condition = ~and_(TaskResult.pass_count == 0, TaskResult.fail_count == 0)
    if limit:
        rows = (await session.execute(select(TaskResult).filter(condition)
                .order_by(TaskResult.execute_time.desc()).offset(limit))).scalars().all()
        for tr in rows:
            await session.delete(tr)
        await session.commit()
    if days:
        n_days_ago = datetime.now() - timedelta(days=days)
        rows = (await session.execute(select(TaskResult).filter(TaskResult.execute_time <= n_days_ago, condition))).scalars().all()
        for tr in rows:
            await session.delete(tr)
        await session.commit()


for _p in ('/{node:int}/tasks/{task_id:int}/{task_result_id:int}/',
           '/{node:int}/tasks/{task_id:int}/',
           '/{node:int}/tasks/'):
    router.add_api_route(_p, tasks_view, methods=['GET', 'POST'], name='tasks')
for _p in ('/{node:int}/tasks/xhr/{action}/{task_id:int}/{task_result_id:int}/',
           '/{node:int}/tasks/xhr/{action}/{task_id:int}/',
           '/{node:int}/tasks/xhr/{action}/'):
    router.add_api_route(_p, tasks_xhr, methods=['GET', 'POST'], name='tasks.xhr')
