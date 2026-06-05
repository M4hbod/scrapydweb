# coding: utf-8
"""Servers overview page (ports views/overview/servers.py)."""
from fastapi import APIRouter, Depends, Request

from ..context import NodeContext, compute_features, get_node_context, DEFAULT_LATEST_VERSION
from ..db import get_metadata
from ..scheduler import safe_get_jobs, scheduler
from ..templating import render
from ..urls import safe_url_for as u

router = APIRouter()

_pageview = {'n': 1}


async def servers(request: Request, node: int, opt: str = None, project: str = None,
                  version_job: str = None, spider: str = None,
                  ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    amount = ctx.SCRAPYD_SERVERS_AMOUNT
    flashes = []

    _pageview['n'] += 1
    pageview = _pageview['n']
    if amount > 1 and not (pageview > 2 and pageview % 100):
        if not app.state.settings.get('ENABLE_AUTH', False):
            flashes.append(('info', "Set 'ENABLE_AUTH = True' to enable basic auth for web UI"))
        if ctx.IS_LOCAL_SCRAPYD_SERVER and not app.state.settings.get('ENABLE_LOGPARSER', False):
            flashes.append(('warning', "Set 'ENABLE_LOGPARSER = True' to run LogParser as a subprocess at startup"))
        if not app.state.settings.get('ENABLE_MONITOR', False):
            flashes.append(('info', "Set 'ENABLE_MONITOR = True' to enable the monitor feature"))

    if request.method == 'POST':
        form = await request.form()
        selected_nodes = [n for n in range(1, amount + 1) if form.get(str(n)) == 'on']
    else:
        selected_nodes = [1] if amount == 1 else []

    meta = await get_metadata()
    any_jobs = any(j.next_run_time for j in safe_get_jobs('default'))
    FEATURES = compute_features(app.state.settings, ctx, meta.get('jobs_style'), any_jobs, scheduler.state)

    page = dict(
        node=node, opt=opt, project=project, version_job=version_job, spider=spider,
        url='http://%s/daemonstatus.json' % ctx.SCRAPYD_SERVER,
        selected_nodes=selected_nodes, IS_IE_EDGE=ctx.IS_IE_EDGE, pageview=pageview,
        FEATURES=FEATURES, DEFAULT_LATEST_VERSION=DEFAULT_LATEST_VERSION,
        url_daemonstatus=u(app, 'api', node=node, opt='daemonstatus'),
        url_getreports=u(app, 'clusterreports', node=node, project='PROJECT_PLACEHOLDER',
                         spider='SPIDER_PLACEHOLDER', job='JOB_PLACEHOLDER'),
        url_liststats=u(app, 'api', node=node, opt='liststats', project='PROJECT_PLACEHOLDER',
                        version_spider_job='JOB_PLACEHOLDER'),
        url_listprojects=u(app, 'api', node=node, opt='listprojects'),
        url_listversions=u(app, 'api', node=node, opt='listversions', project='PROJECT_PLACEHOLDER'),
        url_listspiders=u(app, 'api', node=node, opt='listspiders', project='PROJECT_PLACEHOLDER',
                          version_spider_job='VERSION_PLACEHOLDER'),
        url_listjobs=u(app, 'api', node=node, opt='listjobs', project='PROJECT_PLACEHOLDER'),
        url_deploy=u(app, 'deploy', node=node),
        url_schedule=u(app, 'schedule', node=node, project='PROJECT_PLACEHOLDER',
                       version='VERSION_PLACEHOLDER', spider='SPIDER_PLACEHOLDER'),
        url_stop=u(app, 'multinode', node=node, opt='stop', project='PROJECT_PLACEHOLDER',
                   version_job='JOB_PLACEHOLDER'),
        url_delversion=u(app, 'multinode', node=node, opt='delversion', project='PROJECT_PLACEHOLDER',
                         version_job='VERSION_PLACEHOLDER'),
        url_delproject=u(app, 'multinode', node=node, opt='delproject', project='PROJECT_PLACEHOLDER'),
    )
    return render(request, 'scrapydweb/servers.html', node, ctx, page=page, flashes=flashes)


for _p in ('/{node:int}/servers/getreports/{project}/{spider}/{version_job}/',
           '/{node:int}/servers/{opt}/{project}/{version_job}/{spider}/',
           '/{node:int}/servers/{opt}/{project}/{version_job}/',
           '/{node:int}/servers/{opt}/{project}/',
           '/{node:int}/servers/{opt}/',
           '/{node:int}/servers/'):
    router.add_api_route(_p, servers, methods=['GET', 'POST'], name='servers')
