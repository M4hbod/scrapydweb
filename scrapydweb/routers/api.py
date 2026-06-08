# coding: utf-8
"""Scrapyd JSON API proxy (ports views/api.py)."""
import asyncio
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..common import get_now_string
from ..context import DEFAULT_LATEST_VERSION, NodeContext, get_node_context
from ..services.scrapyd import ERROR, NA, OK, request_scrapyd

router = APIRouter()

API_MAP = dict(start='schedule', stop='cancel', forcestop='cancel')


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
    return js


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
            await asyncio.sleep(0 if request.app.state.settings.get('TESTING') else 2)
    return _handle_result(js, status_code, opt, project, version_spider_job, ctx.SCRAPYD_SERVER)


async def api(request: Request, opt: str, project: str = None, version_spider_job: str = None,
              ctx: NodeContext = Depends(get_node_context)):
    return JSONResponse(await call_api(request, ctx, opt, project, version_spider_job))


for _path in ('/{node:int}/api/{opt}/{project}/{version_spider_job}/',
              '/{node:int}/api/{opt}/{project}/',
              '/{node:int}/api/{opt}/'):
    router.add_api_route(_path, api, methods=['GET', 'POST'], name='api')


# ---- header global search (queries the local jobs DB across nodes) ----
from ..services.dashboard import search_jobs  # noqa: E402


async def search(request: Request, node: int, q: str = '',
                 ctx: NodeContext = Depends(get_node_context)):
    return JSONResponse({'results': await search_jobs(request.app, q)})


router.add_api_route('/{node:int}/search/', search, methods=['GET'], name='search')
