# coding: utf-8
"""Async timer-task executor (ports views/operations/execute_task.py).

Registered as the AsyncIOScheduler job func. For each selected node it posts the
task's spider settings to that node's Scrapyd schedule.json directly (httpx),
with one retry round, and records TaskResult / TaskJobResult rows.
"""
import asyncio
import json
import logging
import re
import traceback

from sqlalchemy import select

from ..common import get_now_string
from ..context import DEFAULT_LATEST_VERSION
from ..db import SessionLocal
from ..models import Task, TaskJobResult, TaskResult
from ..scheduler import scheduler
from .scrapyd import request_scrapyd

apscheduler_logger = logging.getLogger('apscheduler')
EXTRACT_URL_SERVER_PATTERN = re.compile(r'//(.+?:\d+)')

_app = None


def set_app(app):
    global _app
    _app = app


class TaskExecutor:
    def __init__(self, app, task_id, task_name, project, version, spider, settings_arguments, selected_nodes):
        self.app = app
        self.task_id = task_id
        self.task_name = task_name
        self.project = project
        self.version = version
        self.spider = spider
        self.settings_arguments = settings_arguments
        self.selected_nodes = selected_nodes
        self.data = dict(self.settings_arguments)
        self.data['project'] = project
        if version != DEFAULT_LATEST_VERSION:
            self.data['_version'] = version
        self.data['spider'] = spider
        self.data['jobid'] = 'task_%s_%s' % (task_id, get_now_string())
        self.task_result_id = None
        self.pass_count = 0
        self.fail_count = 0
        self.sleep_seconds_before_retry = 3
        self.nodes_to_retry = []
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def servers(self):
        return self.app.state.settings.get('SCRAPYD_SERVERS', []) or ['127.0.0.1:6800']

    @property
    def auths(self):
        return self.app.state.settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None]

    async def main(self):
        await self._create_task_result()
        for index, nodes in enumerate([self.selected_nodes, self.nodes_to_retry]):
            if not nodes:
                continue
            if index == 1:
                await asyncio.sleep(self.sleep_seconds_before_retry)
            for node in list(nodes):
                result = await self._schedule(node)
                if result:
                    if result['status'] == 'ok':
                        self.pass_count += 1
                    else:
                        self.fail_count += 1
                    await self._insert_job_result(result)
        await self._update_task_result()

    async def _create_task_result(self):
        async with SessionLocal() as session:
            tr = TaskResult(task_id=self.task_id)
            session.add(tr)
            await session.commit()
            self.task_result_id = tr.id

    async def _schedule(self, node):
        server = self.servers[node - 1]
        auth = self.auths[node - 1]
        url = 'http://%s/schedule.json' % server
        js = {}
        try:
            status_code, js = await request_scrapyd(self.app.state.http_client, url, data=self.data,
                                                    auth=auth, as_json=True)
            assert status_code == 200 and js.get('status') == 'ok', "Request got %s" % js
        except Exception as err:
            if node not in self.nodes_to_retry:
                apscheduler_logger.warning("Fail to execute task #%s on node %s, would retry later: %s",
                                           self.task_id, node, err)
                self.nodes_to_retry.append(node)
                return {}
            apscheduler_logger.error("Fail to execute task #%s on node %s, no more retries: %s",
                                     self.task_id, node, traceback.format_exc())
            js.setdefault('url', url)
            js.setdefault('status_code', -1)
            js.setdefault('status', 'error')
        js.update(node=node)
        return js

    async def _insert_job_result(self, js):
        async with SessionLocal() as session:
            tr = (await session.execute(select(TaskResult).filter_by(id=self.task_result_id))).scalar_one_or_none()
            if not tr:
                return
            m = re.search(EXTRACT_URL_SERVER_PATTERN, js.get('url', ''))
            tjr = TaskJobResult(
                task_result_id=self.task_result_id, node=js['node'],
                server=m.group(1) if m else self.servers[js['node'] - 1],
                status_code=js['status_code'], status=js['status'],
                result=js.get('jobid', '') or js.get('message', '') or js.get('exception', ''))
            session.add(tjr)
            await session.commit()

    async def _update_task_result(self):
        async with SessionLocal() as session:
            tr = (await session.execute(select(TaskResult).filter_by(id=self.task_result_id))).scalar_one_or_none()
            if tr:
                tr.fail_count = self.fail_count
                tr.pass_count = self.pass_count
                await session.commit()


async def execute_task(task_id):
    if _app is None:
        apscheduler_logger.error("execute_task: app not set")
        return
    async with SessionLocal() as session:
        task = (await session.execute(select(Task).filter_by(id=task_id))).scalar_one_or_none()
    if not task:
        job = scheduler.get_job(str(task_id))
        if job:
            job.remove()
        apscheduler_logger.error("apscheduler_job #%s removed since task not exist.", task_id)
        return
    executor = TaskExecutor(
        _app, task_id=task_id, task_name=task.name, project=task.project, version=task.version,
        spider=task.spider, settings_arguments=json.loads(task.settings_arguments),
        selected_nodes=json.loads(task.selected_nodes))
    try:
        await executor.main()
    except Exception:
        apscheduler_logger.error(traceback.format_exc())
