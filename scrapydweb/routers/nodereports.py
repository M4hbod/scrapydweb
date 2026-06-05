# coding: utf-8
"""Node reports (ports views/dashboard/node_reports.py)."""
from fastapi import APIRouter, Depends, Request

from ..context import NodeContext, get_node_context
from ..services.scrapyd import request_scrapyd
from ..templating import render
from ..urls import safe_url_for as u
from .jobs import _parse

router = APIRouter()


@router.get('/{node:int}/nodereports/', name='nodereports')
async def nodereports(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    url = 'http://%s/jobs' % ctx.SCRAPYD_SERVER
    status_code, text = await request_scrapyd(app.state.http_client, url, auth=ctx.AUTH, as_json=False)
    jobs = _parse(text) if status_code == 200 else []
    pending, running, finished = [], [], []
    for job in jobs:
        if not job['start']:
            pending.append(job)
        elif job['finish']:
            finished.append(job)
        else:
            running.append(job)
    limit = app.state.settings.get('JOBS_FINISHED_JOBS_LIMIT', 0)
    finished = finished[::-1][:limit] if limit > 0 else finished[::-1]
    page = dict(
        node=node, url=u(app, 'jobs', node=node, listjobs='True'),
        pending_jobs=pending, running_jobs=running, finished_jobs=finished,
        url_report=u(app, 'log', node=node, opt='report', project='PROJECT_PLACEHOLDER',
                     spider='SPIDER_PLACEHOLDER', job='JOB_PLACEHOLDER'),
        url_schedule=u(app, 'schedule', node=node),
    )
    return render(request, 'scrapydweb/node_reports.html', node, ctx, page=page)
