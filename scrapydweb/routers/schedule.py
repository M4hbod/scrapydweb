# coding: utf-8
"""Run Spider / Timer Task scheduling (ports views/operations/schedule.py)."""
from collections import OrderedDict
from datetime import datetime
import io
import json
import logging
from math import ceil
import os
import pickle
import re
import shlex
import traceback

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from ..common import get_now_string, json_dumps
from ..context import DEFAULT_LATEST_VERSION, NodeContext, get_node_context
from ..db import SessionLocal
from ..models import Task
from ..scheduler import scheduler
from ..services.scrapyd import request_scrapyd
from ..services.tasks import execute_task
from ..vars import LEGAL_NAME_PATTERN, RUN_SPIDER_HISTORY_LOG, SCHEDULE_ADDITIONAL, SCHEDULE_PATH, STRICT_NAME_PATTERN, UA_DICT
from ..services.deploy_utils import slot

router = APIRouter()
apscheduler_logger = logging.getLogger('apscheduler')
OK, ERROR = 'ok', 'error'
NA = 'N/A'


def generate_cmd(auth, url, data):
    parts = ['curl -u %s:%s %s' % (auth[0], auth[1], url) if auth else 'curl %s' % url]
    for key, value in data.items():
        if key == 'setting':
            for v in value:
                # quote + url-encode values with whitespace/quotes so the cmd stays copy-pasteable
                flag = '--data-urlencode' if re.search(r'[\s"\']', v) else '-d'
                parts.append('%s %s' % (flag, shlex.quote('setting=%s' % v)))
        elif key != '__task_data':
            parts.append('-d %s' % shlex.quote('%s=%s' % (key, value)))
    return ' \\\r\n'.join(parts)


@router.get('/schedule/history/', name='schedule.history')
async def history():
    return FileResponse(RUN_SPIDER_HISTORY_LOG, media_type='text/plain')




# ----------------------------------------------------------------- ScheduleView (form / edit)
# ----------------------------------------------------------------- ScheduleCheckView
def _get_int(form, key, default, minimum):
    value = form.get(key) or default
    try:
        return max(minimum, int(ceil(float(value))))
    except (TypeError, ValueError):
        return default


async def schedule_check(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    form = await request.form()
    data = OrderedDict()
    for key, d in [('project', 'projectname'), ('_version', DEFAULT_LATEST_VERSION), ('spider', 'spidername')]:
        data[key] = form.get(key, d)
    if data['_version'] == DEFAULT_LATEST_VERSION:
        data.pop('_version')
    jobid = form.get('jobid') or get_now_string()
    data['jobid'] = re.sub(LEGAL_NAME_PATTERN, '-', jobid)
    data['setting'] = []
    ua = UA_DICT.get(form.get('USER_AGENT', ''), '')
    if ua:
        data['setting'].append('USER_AGENT=%s' % ua)
    for key in ['ROBOTSTXT_OBEY', 'COOKIES_ENABLED', 'CONCURRENT_REQUESTS', 'DOWNLOAD_DELAY']:
        value = form.get(key, '')
        if value:
            data['setting'].append("%s=%s" % (key, value))
    additional = (form.get('additional', '') or '').strip()
    if additional:
        parts = [i.strip() for i in re.split(r'-d\s+', re.sub(r'[\r\n]', ' ', additional)) if i.strip()]
        for part in parts:
            part = re.sub(r'\s*=\s*', '=', part)
            if '=' not in part:
                continue
            m_setting = re.match(r'setting=([A-Z_]{6,31}=.+)', part)
            if m_setting:
                data['setting'].append(m_setting.group(1))
                continue
            m_arg = re.match(r'([a-zA-Z_][0-9a-zA-Z_]*)=(.+)', part)
            if m_arg and m_arg.group(1) != 'setting':
                data[m_arg.group(1)] = m_arg.group(2)
    # Structured payloads from the SPA -- no '-d' textarea quirks (digit keys, values containing ' -d ').
    try:
        settings_json = json.loads(form.get('settings_json') or '[]')
    except ValueError:
        settings_json = []
    for item in settings_json:
        key, value = str(item.get('key', '')), str(item.get('value', ''))
        if re.match(r'^[A-Z][A-Z0-9_]{0,30}$', key) and value:
            data['setting'].append('%s=%s' % (key, value))
    try:
        args_json = json.loads(form.get('args_json') or '{}')
    except ValueError:
        args_json = {}
    reserved = {'project', '_version', 'spider', 'jobid', 'setting', 'filename', 'checked_amount'}
    for key, value in args_json.items():
        if re.match(r'^[a-zA-Z_][0-9a-zA-Z_]*$', key) and key not in reserved:
            data[key] = str(value)
    data['setting'].sort()
    _version = data.get('_version', 'default-the-latest-version')
    _filename = '{project}_{version}_{spider}'.format(project=data['project'], version=_version, spider=data['spider'])
    filename = '%s.pickle' % re.sub(LEGAL_NAME_PATTERN, '-', _filename)
    with io.open(os.path.join(SCHEDULE_PATH, filename), 'wb') as f:
        f.write(pickle.dumps(data))
    slot.add_data(filename, data)

    if form.get('trigger'):
        data['__task_data'] = dict(
            action=form.get('action') or 'add_fire',
            task_id=int(form.get('task_id') or 0),
            trigger='cron',
            name=form.get('name') or None,
            replace_existing=(form.get('replace_existing', 'True') == 'True'),
            year=form.get('year') or '*', month=form.get('month') or '*', day=form.get('day') or '*',
            week=form.get('week') or '*', day_of_week=form.get('day_of_week') or '*',
            hour=form.get('hour') or '*', minute=form.get('minute') or '0', second=form.get('second') or '0',
            start_date=form.get('start_date') or None, end_date=form.get('end_date') or None,
            timezone=form.get('timezone') or None,
            jitter=_get_int(form, 'jitter', 0, 0),
            misfire_grace_time=_get_int(form, 'misfire_grace_time', 600, 0) or None,
            coalesce=(form.get('coalesce') or 'True') == 'True',
            max_instances=_get_int(form, 'max_instances', 1, 1),
        )
        slot.add_data(filename, data)

    cmd = generate_cmd(ctx.AUTH, 'http://%s/schedule.json' % ctx.SCRAPYD_SERVER,
                       {k: v for k, v in data.items() if k != '__task_data'})
    return JSONResponse({'filename': filename, 'cmd': cmd})


# ----------------------------------------------------------------- ScheduleRunView
async def schedule_run(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    form = await request.form()
    filename = form['filename']
    as_json = True  # the HTML UI is gone; JSON is the only response shape
    servers = ctx.SCRAPYD_SERVERS
    auths = app.state.settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None]

    selected_amount = int(form.get('checked_amount') or 0)
    if selected_amount:
        selected_nodes = [n for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1) if form.get(str(n)) == 'on']
        first = selected_nodes[0]
        url = 'http://%s/schedule.json' % servers[first - 1]
        auth = auths[first - 1]
    else:
        selected_nodes = [node]
        first = node
        url = 'http://%s/schedule.json' % ctx.SCRAPYD_SERVER
        auth = ctx.AUTH

    data = slot.data.get(filename)
    if not data:
        with io.open(os.path.join(SCHEDULE_PATH, filename), 'rb') as f:
            data = pickle.loads(f.read())
    data = dict(data)
    task_data = data.pop('__task_data', {})

    js = {}
    action = 'run'
    add_task_result = False
    add_task_flash = ''
    add_task_error = ''
    add_task_message = ''

    if task_data:
        action = task_data.pop('action')
        task_id = task_data.pop('task_id')
        to_update = task_data.pop('replace_existing') and task_id
        # persist Task row
        async with SessionLocal() as session:
            if to_update:
                task = (await session.execute(select(Task).filter_by(id=task_id))).scalar_one_or_none()
            else:
                task = Task()
            d = dict(data)
            task.project = d.pop('project')
            task.version = d.pop('_version', DEFAULT_LATEST_VERSION)
            task.spider = d.pop('spider')
            task.jobid = d.pop('jobid')
            task.settings_arguments = json_dumps(d, sort_keys=True, indent=None)
            task.selected_nodes = str(selected_nodes)
            task.name = task_data['name']
            task.trigger = task_data['trigger']
            for fld in ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 'minute', 'second',
                        'start_date', 'end_date', 'timezone', 'jitter', 'misfire_grace_time', 'max_instances']:
                setattr(task, fld, task_data[fld])
            task.coalesce = 'True' if task_data['coalesce'] else 'False'
            task.update_time = datetime.now()
            if not to_update:
                # A new task is persisted regardless of whether the apscheduler job is
                # valid (matches legacy behavior; failed jobs leave a re-editable task).
                session.add(task)
                await session.commit()
            else:
                await session.flush()  # stage the update; commit only if add_job succeeds
            task_id = task.id

            kwargs = dict(task_id=task_id)
            task_data['id'] = str(task_id)
            task_data['name'] = task_data['name'] or 'task_%s' % task_id
            postfix = "Click the Running button to pause it. "
            if action == 'add_fire':
                if not to_update:
                    task_data['next_run_time'] = datetime.now()
                postfix = "Reload this page several seconds later to check out the execution result. "
            elif action == 'add_pause':
                task_data['next_run_time'] = None
                postfix = "Click the Paused button to resume it. "
            msg = ''
            try:
                job_instance = scheduler.add_job(func=execute_task, args=None, kwargs=kwargs,
                                                 replace_existing=True, **task_data)
            except Exception as err:
                if to_update:
                    await session.rollback()  # keep the existing task unchanged
                add_task_result = False
                add_task_error = str(err)
                msg = traceback.format_exc()
                apscheduler_logger.error(msg)
            else:
                if to_update:
                    await session.commit()
                if to_update and action == 'add_fire':
                    job_instance.modify(next_run_time=datetime.now())
                add_task_result = True
                msg = u"{target} task #{task_id} ({task_name}) successfully, next run at {nrt}. ".format(
                    target="Update" if to_update else 'Add', task_id=task_id, task_name=task_data['name'],
                    nrt=job_instance.next_run_time or NA)
                add_task_flash = msg + postfix
                apscheduler_logger.warning(msg)  # written to TIMER_TASKS_HISTORY_LOG by the file handler
                job_instance_dict = dict(
                    id=job_instance.id, name=job_instance.name, kwargs=job_instance.kwargs,
                    misfire_grace_time=job_instance.misfire_grace_time, max_instances=job_instance.max_instances,
                    trigger=repr(job_instance.trigger), next_run_time=repr(job_instance.next_run_time))
                apscheduler_logger.warning("%s job_instance: \n%s", "Updated" if to_update else 'Added',
                                           json_dumps(job_instance_dict))
            if 'next_run_time' in task_data:
                task_data['next_run_time'] = str(task_data['next_run_time'] or NA)
            add_task_message = (u"{msg}\nkwargs for execute_task():\n{kwargs}\n\n"
                                u"task_data for scheduler.add_job():\n{task_data}").format(
                msg=msg, kwargs=json_dumps(kwargs), task_data=json_dumps(task_data))
    else:
        status_code, js = await request_scrapyd(app.state.http_client, url, data=data, auth=auth, as_json=True)
        if js.get('status') == OK and js.get('jobid'):
            from ..services.job_versions import record_job_version, resolve_version
            server = servers[first - 1]
            version = await resolve_version(app.state.http_client, server, auth,
                                            data['project'], data.get('_version'))
            await record_job_version(server, data['project'], data['spider'],
                                     js['jobid'], version, source='run')

    # update history
    try:
        with io.open(RUN_SPIDER_HISTORY_LOG, 'r+', encoding='utf-8') as f:
            backup = f.read()
            f.seek(0)
            f.write(os.linesep.join([
                '%s %s <%s>' % ('#' * 50, get_now_string(True), action),
                str([servers[i - 1] for i in selected_nodes]),
                generate_cmd(auth, url, data),
                add_task_message or json_dumps(js), '']) + backup)
    except Exception:
        pass

    # response
    if action in ['add', 'add_fire', 'add_pause']:
        if as_json:
            return JSONResponse(dict(
                status=OK if add_task_result else ERROR, action=action, task_id=task_id,
                flash=add_task_flash, error=add_task_error, message=add_task_message))

    if js.get('status') == OK:
        if as_json:
            return JSONResponse(dict(
                status=OK, js=js, project=data['project'], spider=data['spider'],
                jobid=data['jobid'], version=data.get('_version', DEFAULT_LATEST_VERSION),
                selected_nodes=selected_nodes, first_selected_node=first, filename=filename))
    alert = ("Multinode schedule terminated, since the first selected node returned status: " + js.get('status', '')
             if selected_amount > 1 else "Fail to schedule, got status: " + js.get('status', ''))
    if as_json:
        return JSONResponse(dict(status=ERROR, alert=alert, js=js, message=js.get('message', '')))


async def schedule_xhr(request: Request, node: int, filename: str,
                       ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    data = slot.data.get(filename)
    if not data:
        with io.open(os.path.join(SCHEDULE_PATH, filename), 'rb') as f:
            data = pickle.loads(f.read())
    data = {k: v for k, v in dict(data).items() if k != '__task_data'}
    status_code, js = await request_scrapyd(app.state.http_client,
                                            'http://%s/schedule.json' % ctx.SCRAPYD_SERVER,
                                            data=data, auth=ctx.AUTH, as_json=True)
    if js.get('status') == OK and js.get('jobid'):
        from ..services.job_versions import record_job_version, resolve_version
        version = await resolve_version(app.state.http_client, ctx.SCRAPYD_SERVER, ctx.AUTH,
                                        data['project'], data.get('_version'))
        await record_job_version(ctx.SCRAPYD_SERVER, data['project'], data['spider'],
                                 js['jobid'], version, source='run')
    return JSONResponse(js)


async def schedule_task(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    form = await request.form()
    task_id = form['task_id']
    jobid = form['jobid']
    url = 'http://%s/schedule.json' % ctx.SCRAPYD_SERVER
    async with SessionLocal() as session:
        task = (await session.execute(select(Task).filter_by(id=int(task_id)))).scalar_one_or_none()
    if not task:
        js = dict(url=url, auth=ctx.AUTH, status_code=-1, status='error', message="Task #%s not found" % task_id)
    else:
        data = dict(project=task.project)
        if task.version != DEFAULT_LATEST_VERSION:
            data['_version'] = task.version
        data['spider'] = task.spider
        data['jobid'] = jobid
        data.update(json.loads(task.settings_arguments))
        status_code, js = await request_scrapyd(app.state.http_client, url, data=data, auth=ctx.AUTH, as_json=True)
        if js.get('status') == OK and js.get('jobid'):
            from ..services.job_versions import record_job_version, resolve_version
            version = await resolve_version(app.state.http_client, ctx.SCRAPYD_SERVER, ctx.AUTH,
                                            task.project, task.version)
            await record_job_version(ctx.SCRAPYD_SERVER, task.project, task.spider,
                                     js['jobid'], version, source='task')
    return JSONResponse(js)


# Specific routes MUST be registered before the generic /schedule/{project}/ variants.
router.add_api_route('/{node:int}/schedule/check/', schedule_check, methods=['POST'], name='schedule.check')
router.add_api_route('/{node:int}/schedule/run/', schedule_run, methods=['POST'], name='schedule.run')
router.add_api_route('/{node:int}/schedule/xhr/{filename}/', schedule_xhr, methods=['GET', 'POST'], name='schedule.xhr')
router.add_api_route('/{node:int}/schedule/task/', schedule_task, methods=['POST'], name='schedule.task')
