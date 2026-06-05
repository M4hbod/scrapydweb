# coding: utf-8
"""Cluster reports (ports views/dashboard/cluster_reports.py)."""
from fastapi import APIRouter, Depends, Request
from ..responses import redirect as _redirect

from ..context import NodeContext, get_node_context
from ..templating import render
from ..urls import safe_url_for as u, url_for

router = APIRouter()

_meta = dict(project='', spider='', job='', selected_nodes=[])


async def clusterreports(request: Request, node: int, project: str = None, spider: str = None,
                         job: str = None, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    raw = (project, spider, job)
    selected = []
    if request.method == 'POST':
        form = await request.form()
        selected = [n for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1) if form.get(str(n)) == 'on']
    project = project or _meta['project']
    spider = spider or _meta['spider']
    job = job or _meta['job']
    selected = selected or _meta['selected_nodes']
    _meta.update(project=project, spider=spider, job=job, selected_nodes=selected)

    if all([project, spider, job]):
        if not any(raw):
            return _redirect(url_for(app, 'clusterreports', node=node, project=project,
                                     spider=spider, job=job))
        if not selected:
            return _redirect(u(app, 'servers', node=node, opt='getreports', project=project,
                               spider=spider, version_job=job))
    url_servers = '' if not any([project, spider, job]) else u(
        app, 'servers', node=node, opt='getreports', project=project, spider=spider, version_job=job)
    page = dict(
        node=node, project=project, spider=spider, job=job, selected_nodes=selected,
        url_report=u(app, 'log', node=node, opt='report', project=project, spider=spider, job=job),
        url_servers=url_servers, url_jobs=u(app, 'jobs', node=node),
    )
    return render(request, 'scrapydweb/cluster_reports.html', node, ctx, page=page)


for _p in ('/{node:int}/clusterreports/{project}/{spider}/{job}/', '/{node:int}/clusterreports/'):
    router.add_api_route(_p, clusterreports, methods=['GET', 'POST'], name='clusterreports')
