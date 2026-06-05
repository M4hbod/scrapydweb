# coding: utf-8
"""Synchronous timer-task executor (ports views/operations/execute_task.py).

Runs in the BackgroundScheduler thread (no asyncio loop). For each selected node
it posts the task's spider settings to that node's Scrapyd schedule.json (sync
requests), with one retry round, and records TaskResult / TaskJobResult rows via
a sync session.
"""
import json
import logging
import re
import time
import traceback

from sqlalchemy import select

from ..common import get_now_string, session
from ..context import DEFAULT_LATEST_VERSION
from ..db_sync import SyncSessionLocal
from ..models import Task, TaskJobResult, TaskResult
from ..scheduler import scheduler

apscheduler_logger = logging.getLogger('apscheduler')
EXTRACT_URL_SERVER_PATTERN = re.compile(r'//(.+?:\d+)')

_app = None


def set_app(app):
    global _app
    _app = app


def _settings():
    return _app.state.settings if _app is not None else {}


def _request_scrapyd_sync(url, data, auth):
    try:
        r = session.post(url, data=data, auth=tuple(auth) if auth else None, timeout=60)
    except Exception as err:
        return -1, dict(url=url, status_code=-1, status='error', message=str(err), when=get_now_string(True))
    try:
        js = r.json()
    except ValueError:
        js = dict(status='error', message=r.text)
    js.update(url=url, status_code=r.status_code, when=get_now_string(True))
    js.setdefault('status', 'N/A')
    return r.status_code, js


class TaskExecutor:
    def __init__(self, task_id, task_name, project, version, spider, settings_arguments, selected_nodes):
        s = _settings()
        self.servers = s.get('SCRAPYD_SERVERS', []) or ['127.0.0.1:6800']
        self.auths = s.get('SCRAPYD_SERVERS_AUTHS', []) or [None]
        self.task_id = task_id
        self.task_name = task_name
        self.data = dict(settings_arguments)
        self.data['project'] = project
        if version != DEFAULT_LATEST_VERSION:
            self.data['_version'] = version
        self.data['spider'] = spider
        self.data['jobid'] = 'task_%s_%s' % (task_id, get_now_string())
        self.selected_nodes = selected_nodes
        self.task_result_id = None
        self.pass_count = 0
        self.fail_count = 0
        self.sleep_seconds_before_retry = 3
        self.nodes_to_retry = []

    def main(self):
        with SyncSessionLocal() as s:
            tr = TaskResult(task_id=self.task_id)
            s.add(tr)
            s.commit()
            self.task_result_id = tr.id
        for index, nodes in enumerate([self.selected_nodes, self.nodes_to_retry]):
            if not nodes:
                continue
            if index == 1:
                time.sleep(self.sleep_seconds_before_retry)
            for node in list(nodes):
                result = self._schedule(node)
                if result:
                    if result['status'] == 'ok':
                        self.pass_count += 1
                    else:
                        self.fail_count += 1
                    self._insert_job_result(result)
        with SyncSessionLocal() as s:
            tr = s.execute(select(TaskResult).filter_by(id=self.task_result_id)).scalar_one_or_none()
            if tr:
                tr.fail_count = self.fail_count
                tr.pass_count = self.pass_count
                s.commit()

    def _schedule(self, node):
        server = self.servers[node - 1]
        auth = self.auths[node - 1]
        url = 'http://%s/schedule.json' % server
        js = {}
        try:
            status_code, js = _request_scrapyd_sync(url, self.data, auth)
            assert status_code == 200 and js.get('status') == 'ok', "Request got %s" % js
        except Exception as err:
            if node not in self.nodes_to_retry:
                apscheduler_logger.warning("Fail to execute task #%s (%s) on node %s, would retry later: %s",
                                           self.task_id, self.task_name, node, err)
                self.nodes_to_retry.append(node)
                return {}
            apscheduler_logger.error("Fail to execute task #%s (%s) on node %s, no more retries: %s",
                                     self.task_id, self.task_name, node, traceback.format_exc())
            js.setdefault('url', url)
            js.setdefault('status_code', -1)
            js.setdefault('status', 'error')
        js.update(node=node)
        return js

    def _insert_job_result(self, js):
        with SyncSessionLocal() as s:
            if not s.execute(select(TaskResult).filter_by(id=self.task_result_id)).scalar_one_or_none():
                return
            m = re.search(EXTRACT_URL_SERVER_PATTERN, js.get('url', ''))
            s.add(TaskJobResult(
                task_result_id=self.task_result_id, node=js['node'],
                server=m.group(1) if m else self.servers[js['node'] - 1],
                status_code=js['status_code'], status=js['status'],
                result=js.get('jobid', '') or js.get('message', '') or js.get('exception', '')))
            s.commit()


def execute_task(task_id):
    with SyncSessionLocal() as s:
        task = s.execute(select(Task).filter_by(id=task_id)).scalar_one_or_none()
    if not task:
        job = scheduler.get_job(str(task_id))
        if job:
            job.remove()
        apscheduler_logger.error("apscheduler_job #%s removed since task not exist.", task_id)
        return
    executor = TaskExecutor(task_id=task_id, task_name=task.name, project=task.project, version=task.version,
                            spider=task.spider, settings_arguments=json.loads(task.settings_arguments),
                            selected_nodes=json.loads(task.selected_nodes))
    try:
        executor.main()
    except Exception:
        apscheduler_logger.error(traceback.format_exc())
