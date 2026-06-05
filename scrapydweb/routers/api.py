# coding: utf-8
"""Scrapyd JSON API proxy (ports views/api.py)."""
import asyncio
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from logparser import __version__ as LOGPARSER_VERSION

from ..common import get_now_string
from ..context import DEFAULT_LATEST_VERSION, NodeContext, get_node_context
from ..services.scrapyd import ERROR, NA, OK, request_scrapyd

router = APIRouter()

API_MAP = dict(start='schedule', stop='cancel', forcestop='cancel', liststats='logs/stats')


def _build_url(ctx, opt, project, version_spider_job):
    url = 'http://{}/{}.json'.format(ctx.SCRAPYD_SERVER, API_MAP.get(opt, opt))
    if opt in ['listversions', 'listjobs']:
        url += '?project=%s' % project
    elif opt == 'listspiders':
        if version_spider_job == DEFAULT_LATEST_VERSION:
            url += '?project=%s' % project
        else:
            url += '?project=%s&_version=%s' % (project, version_spider_job)
    return url


def _build_data(opt, project, version_spider_job):
    data = dict(project=project)
    if opt == 'start':
        data['spider'] = version_spider_job
        data['jobid'] = get_now_string()
    elif opt in ['stop', 'forcestop']:
        data['job'] = version_spider_job
    elif opt == 'delversion':
        data['version'] = version_spider_job
    elif opt == 'delproject':
        pass
    else:
        data = None
    return data


def _handle_result(js, status_code, opt, project, version_spider_job, server):
    if status_code != 200:
        if opt == 'liststats':
            if project and version_spider_job:
                if status_code == 404:
                    js = dict(status=OK, tip="'pip install logparser' and run command 'logparser'")
            else:
                js['tip'] = ("'pip install logparser' on host '%s' and run command 'logparser' "
                             "to show crawled_pages and scraped_items. ") % server
        else:
            js['tip'] = "Make sure that your Scrapyd server is accessable. "
    elif js['status'] != OK:
        if re.search('No such file|no active project', js.get('message', '')):
            js['tip'] = "Maybe the project had been deleted, check out the Projects page. "
        elif opt == 'listversions':
            js['tip'] = ("Maybe it's caused by failing to compare versions, "
                         "you can check out the HELP section in the Deploy Project page for more info, "
                         "and solve the problem in the Projects page. ")
        elif opt == 'listspiders' and re.search("TypeError: 'tuple'", js.get('message', '')):
            js['tip'] = "Maybe it's a broken project, check out the Projects page to delete it. "
    elif opt == 'liststats':
        if js.get('logparser_version') != LOGPARSER_VERSION:
            if project and version_spider_job:
                tip = "'pip install --upgrade logparser' to update LogParser to v%s" % LOGPARSER_VERSION
                js = dict(status=OK, tip=tip)
            else:
                js['tip'] = ("'pip install --upgrade logparser' on host '%s' and run command 'logparser' "
                             "to update LogParser to v%s") % (server, LOGPARSER_VERSION)
                js['status'] = ERROR
        elif project and version_spider_job:
            js = _extract_pages_items(js, project, version_spider_job)
    return js


def _extract_pages_items(js, project, version_spider_job):
    details = None
    if project in js['datas']:
        for spider in js['datas'][project]:
            for jobid in js['datas'][project][spider]:
                if jobid == version_spider_job:
                    details = js['datas'][project][spider][version_spider_job]
                    js['project'] = project
                    js['spider'] = spider
                    js['jobid'] = jobid
                    break
    if not details:
        details = dict(pages=NA, items=NA)
    details.setdefault('project', project)
    details.setdefault('spider', NA)
    details.setdefault('jobid', version_spider_job)
    details['logparser_version'] = js.get('logparser_version', None)
    return dict(status=OK, details=details)


async def call_api(request, ctx, opt, project=None, version_spider_job=None):
    """Run a Scrapyd API call and return the result dict (shared by api/projects/nodereports)."""
    url = _build_url(ctx, opt, project, version_spider_job)
    data = _build_data(opt, project, version_spider_job)
    timeout = 3 if opt == 'daemonstatus' else 60
    times = 2 if opt == 'forcestop' else 1
    client = request.app.state.http_client
    js = {}
    for __ in range(times):
        status_code, js = await request_scrapyd(client, url, data=data, auth=ctx.AUTH, as_json=True, timeout=timeout)
        if times != 1:
            js['times'] = times
            await asyncio.sleep(2)
    return _handle_result(js, status_code, opt, project, version_spider_job, ctx.SCRAPYD_SERVER)


async def api(request: Request, opt: str, project: str = None, version_spider_job: str = None,
              ctx: NodeContext = Depends(get_node_context)):
    return JSONResponse(await call_api(request, ctx, opt, project, version_spider_job))


for _path in ('/{node:int}/api/{opt}/{project}/{version_spider_job}/',
              '/{node:int}/api/{opt}/{project}/',
              '/{node:int}/api/{opt}/'):
    router.add_api_route(_path, api, methods=['GET', 'POST'], name='api')
