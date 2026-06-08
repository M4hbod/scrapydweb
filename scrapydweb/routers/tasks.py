# coding: utf-8
"""Timer Tasks pages + xhr (ports views/overview/tasks.py)."""
from datetime import datetime, timedelta
import json
import logging
import traceback

import io

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import and_, func, select


from ..db import Pagination, SessionLocal, ensure_tables, get_metadata, set_metadata
from ..models import Task, TaskJobResult, TaskResult
from ..scheduler import STATE_PAUSED, STATE_RUNNING, safe_get_jobs, scheduler
from ..urls import safe_url_for as u
from ..vars import SCHEDULER_STATE_DICT, TIMER_TASKS_HISTORY_LOG

router = APIRouter()
apscheduler_logger = logging.getLogger('apscheduler')
OK, ERROR, NA = 'ok', 'error', 'N/A'


def _rm_micro(dt):
    return str(dt)[:19]


@router.get('/tasks/history/', name='tasks.history')
async def history(request: Request):
    try:
        with io.open(TIMER_TASKS_HISTORY_LOG, encoding='utf-8') as f:
            log = f.read()
    except Exception:
        log = ''
    return JSONResponse(dict(status='ok', text=log))


async def _paginate(session, stmt_count, stmt_items, page, per_page):
    total = (await session.execute(stmt_count)).scalar()
    rows = (await session.execute(stmt_items.limit(per_page).offset((page - 1) * per_page))).scalars().all()
    return rows, total


async def tasks_xhr(request: Request, node: int, action: str, task_id: int = None, task_result_id: int = None):
    # DB/scheduler only -- no node context needed (works with zero servers)
    await ensure_tables()  # self-heal if the DB was recreated
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
            js['url_jump'] = '/tasks'  # SPA route
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


for _p in ('/{node:int}/tasks/xhr/{action}/{task_id:int}/{task_result_id:int}/',
           '/{node:int}/tasks/xhr/{action}/{task_id:int}/',
           '/{node:int}/tasks/xhr/{action}/'):
    router.add_api_route(_p, tasks_xhr, methods=['GET', 'POST'], name='tasks.xhr')
