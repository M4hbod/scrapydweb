# coding: utf-8
"""Multinode results (ports views/overview/multinode.py)."""
from fastapi import APIRouter, Depends, Request

from ..context import NodeContext, get_node_context
from ..templating import render
from ..urls import safe_url_for as u

router = APIRouter()


async def multinode(request: Request, node: int, opt: str, project: str, version_job: str = None,
                    ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    form = await request.form()
    selected_nodes = [n for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1) if form.get(str(n)) == 'on']
    first = selected_nodes[0] if selected_nodes else node
    url_xhr = u(app, 'api', node=first, opt=opt, project=project, version_spider_job=version_job)
    if opt == 'stop':
        title = "Stop Job (%s) of Project (%s)" % (project, version_job)
        url_servers = u(app, 'servers', node=node, opt='listjobs', project=project)
        btn_servers = "Servers &raquo; List Running Jobs"
    elif opt == 'delversion':
        title = "Delete Version (%s) of Project (%s)" % (version_job, project)
        url_servers = u(app, 'servers', node=node, opt='listversions', project=project)
        btn_servers = "Servers &raquo; List Versions"
    else:
        title = "Delete Project (%s)" % project
        url_servers = u(app, 'servers', node=node, opt='listprojects', project=project)
        btn_servers = "Servers &raquo; List Projects"
    page = dict(
        node=node, title=title, opt=opt, project=project, version_job=version_job,
        selected_nodes=selected_nodes, url_xhr=url_xhr, url_servers=url_servers, btn_servers=btn_servers,
        url_projects_list=[u(app, 'projects', node=n) for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1)],
    )
    return render(request, 'scrapydweb/multinode_results.html', node, ctx, page=page)


for _p in ('/{node:int}/multinode/{opt}/{project}/{version_job}/', '/{node:int}/multinode/{opt}/{project}/'):
    router.add_api_route(_p, multinode, methods=['POST'], name='multinode')
