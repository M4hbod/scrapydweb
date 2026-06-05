# coding: utf-8
"""Logs directory listing (ports views/files/logs.py)."""
import re

from fastapi import APIRouter, Depends, Request

from ..context import NodeContext, get_node_context, DEFAULT_LATEST_VERSION
from ..common import get_job_without_ext
from ..services.scrapyd import request_scrapyd
from ..templating import render
from ..urls import safe_url_for as u
from ..vars import DIRECTORY_KEYS, DIRECTORY_PATTERN, HREF_NAME_PATTERN

router = APIRouter()


async def logs(request: Request, node: int, project: str = None, spider: str = None,
               ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    url = 'http://{}/logs/{}{}'.format(ctx.SCRAPYD_SERVER,
                                       '%s/' % project if project else '',
                                       '%s/' % spider if spider else '')
    status_code, text = await request_scrapyd(app.state.http_client, url, auth=ctx.AUTH, as_json=False)
    if status_code != 200 or not re.search(r'Directory listing for /logs/', text):
        fail = 'scrapydweb/fail_mobileui.html' if ctx.USE_MOBILEUI else 'scrapydweb/fail.html'
        return render(request, fail, node, ctx, page=dict(
            node=node, url=url, status_code=status_code, text=text,
            tip="Click the above link to make sure your Scrapyd server is accessable. "))

    rows = [dict(zip(DIRECTORY_KEYS, row)) for row in re.findall(DIRECTORY_PATTERN, text)]
    for row in rows:
        row['href'], row['filename'] = re.search(HREF_NAME_PATTERN, row['filename']).groups()
        if not row['href'].endswith('/'):
            row['href'] = url + row['href']
        if project and spider:
            row['url_stats'] = u(app, 'log', node=node, opt='stats', project=project,
                                 spider=spider, job=row['filename'], with_ext='True')
            row['url_utf8'] = '' if row['filename'].endswith('.json') else u(
                app, 'log', node=node, opt='utf8', project=project, spider=spider,
                job=row['filename'], with_ext='True')
            row['url_clusterreports'] = u(app, 'clusterreports', node=node, project=project,
                                          spider=spider, job=get_job_without_ext(row['filename']))
    if project and spider:
        url_schedule = u(app, 'schedule', node=node, project=project, version=DEFAULT_LATEST_VERSION, spider=spider)
        url_multinode_run = u(app, 'servers', node=node, opt='schedule', project=project,
                              version_job=DEFAULT_LATEST_VERSION, spider=spider)
    else:
        url_schedule = url_multinode_run = ''
    return render(request, 'scrapydweb/logs_items.html', node, ctx, page=dict(
        node=node, title='logs', project=project, spider=spider, url=url,
        url_schedule=url_schedule, url_multinode_run=url_multinode_run, rows=rows))


for _p in ('/{node:int}/logs/{project}/{spider}/', '/{node:int}/logs/{project}/', '/{node:int}/logs/'):
    router.add_api_route(_p, logs, methods=['GET'], name='logs')
