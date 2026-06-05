# coding: utf-8
"""Projects (ports views/files/projects.py)."""
import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..common import json_dumps
from ..context import NodeContext, get_node_context
from ..templating import render
from ..urls import safe_url_for as u
from .api import call_api

router = APIRouter()
OK = 'ok'


def _fail_template(ctx):
    return 'scrapydweb/fail_mobileui.html' if ctx.USE_MOBILEUI else 'scrapydweb/fail.html'


async def projects(request: Request, node: int, opt: str = 'listprojects', project: str = None,
                   version_spider_job: str = None, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    js = await call_api(request, ctx, opt, project, version_spider_job)

    if js['status'] != OK:
        if opt == 'listversions':
            page = dict(url=js['url'], status=js['status'], url_deploy=u(app, 'deploy', node=node),
                        url_delproject=u(app, 'projects', node=node, opt='delproject', project=project),
                        project=project, text=json_dumps(js), tip=js.get('tip', ''))
            return render(request, 'scrapydweb/listversions_error.html', node, ctx, page=page)
        if request.method == 'POST':
            return HTMLResponse('<a class="request" target="_blank" href="%s">REQUEST</a>'
                                '<em class="fail"> got status: %s</em>' % (str(request.url), js['status']))
        alert = 'REQUEST got status: %s' % js['status']
        message = js.get('message', '')
        if message:
            js['message'] = 'See details below'
        return render(request, _fail_template(ctx), node, ctx,
                      page=dict(node=node, alert=alert, text=json_dumps(js), message=message))

    if opt in ('delproject', 'delversion'):
        return HTMLResponse('<em class="pass">%s deleted</em>' % ('project' if opt == 'delproject' else 'version'))

    if opt == 'listprojects':
        results = [(p, u(app, 'projects', node=node, opt='listversions', project=p)) for p in js['projects']]
        return render(request, 'scrapydweb/projects.html', node, ctx, page=dict(
            node=node, url=js['url'], node_name=js['node_name'], results=results,
            url_deploy=u(app, 'deploy', node=node)))

    if opt == 'listspiders':
        results = [(s, u(app, 'schedule', node=node, project=project, version=version_spider_job, spider=s),
                    u(app, 'servers', node=node, opt='schedule', project=project,
                      version_job=version_spider_job, spider=s)) for s in js['spiders']]
        return render(request, 'scrapydweb/listspiders.html', node, ctx, page=dict(node=node, results=results))

    # listversions
    results = []
    for version in js['versions']:
        try:
            readable = ' (%s)' % datetime.datetime.fromtimestamp(int(version)).isoformat()
        except Exception:
            readable = ''
        results.append((version, readable,
                        u(app, 'projects', node=node, opt='listspiders', project=project, version_spider_job=version),
                        u(app, 'servers', node=node, opt='delversion', project=project, version_job=version),
                        u(app, 'projects', node=node, opt='delversion', project=project, version_spider_job=version)))
    return render(request, 'scrapydweb/listversions.html', node, ctx, page=dict(
        node=node, project=project, results=results,
        url_multinode_delproject=u(app, 'servers', node=node, opt='delproject', project=project),
        url_delproject=u(app, 'projects', node=node, opt='delproject', project=project)))


for _p in ('/{node:int}/projects/{opt}/{project}/{version_spider_job}/',
           '/{node:int}/projects/{opt}/{project}/',
           '/{node:int}/projects/'):
    router.add_api_route(_p, projects, methods=['GET', 'POST'], name='projects')
