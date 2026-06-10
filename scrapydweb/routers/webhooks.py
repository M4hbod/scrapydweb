# coding: utf-8
"""GitHub push webhook -> auto-deploy a project.

POST /api/webhooks/github/{project_id}: authenticated by X-Hub-Signature-256
(HMAC-SHA256 of the raw body with the project's webhook_secret) -- the session
middleware exempts this path (see app.py). The clone+build runs in
BackgroundTasks (GitHub times webhooks out at 10s), so the endpoint answers 202
with a pending DeployRecord id. The project's deploy config (repo_url, ref,
access_token, default_nodes) lives on the Project row (routers/projects.py).
"""
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..db import SessionLocal
from ..models import Project

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run_webhook_deploy(app, snap, record_id):
    """Background: clone, build, deploy to the project's nodes, finalize the record."""
    from .deploy import deploy_egg_to_nodes, finish_deploy_record
    from .deploy_ci import _clone_and_build

    testing = bool(app.state.settings.get('TESTING'))
    try:
        built = await run_in_threadpool(
            _clone_and_build, snap['repo_url'], snap['ref'], snap['access_token'],
            snap['name'], '', testing)  # version '' -> timestamp + short SHA
        if built.get('status') != 'built':
            await finish_deploy_record(record_id, 'error', message=built.get('message', ''))
            return
        overall, results, _first_js = await deploy_egg_to_nodes(
            app, snap['nodes'], built['project'], built['version'],
            built['egg_bytes'], built['eggname'])
        await finish_deploy_record(record_id, overall, results=results,
                                   version=built['version'], eggname=built['eggname'])
    except Exception:
        logger.exception('webhook deploy for project %r failed', snap['name'])
        await finish_deploy_record(record_id, 'error', message='webhook deploy failed')


@router.post('/api/webhooks/github/{project_id:int}', name='webhooks.github')
async def github_webhook(request: Request, project_id: int, background_tasks: BackgroundTasks):
    raw = await request.body()
    async with SessionLocal() as s:
        p = (await s.execute(select(Project).filter_by(id=project_id))).scalar_one_or_none()
        if p is None or not p.enabled or not p.webhook_secret:
            return JSONResponse({'status': 'error', 'message': 'unknown project'}, status_code=404)
        snap = dict(name=p.name, repo_url=p.repo_url, ref=p.ref or 'main',
                    access_token=p.access_token, webhook_secret=p.webhook_secret,
                    nodes=json.loads(p.default_nodes_json or '[1]'))

    expected = 'sha256=' + hmac.new(snap['webhook_secret'].encode('utf-8'),
                                    raw, hashlib.sha256).hexdigest()
    supplied = request.headers.get('X-Hub-Signature-256', '')
    if not (supplied and hmac.compare_digest(supplied, expected)):
        return JSONResponse({'status': 'error', 'message': 'invalid signature'}, status_code=401)

    event = request.headers.get('X-GitHub-Event', 'push')
    if event == 'ping':
        return JSONResponse({'status': 'ok', 'message': 'pong'})
    if event != 'push':
        return JSONResponse({'status': 'ok', 'message': 'ignored event %r' % event})

    try:
        payload = json.loads(raw or b'{}')
    except ValueError:
        return JSONResponse({'status': 'error', 'message': 'invalid JSON payload'}, status_code=400)
    ref = payload.get('ref', '')
    if ref and ref != 'refs/heads/%s' % snap['ref']:
        return JSONResponse({'status': 'ok', 'message': 'ignored ref %r (deploying %r)'
                             % (ref, snap['ref'])})

    from .deploy import record_deploy
    record_id = await record_deploy('webhook', snap['name'], None, None, 'pending',
                                    actor='webhook:%s' % snap['name'])
    background_tasks.add_task(_run_webhook_deploy, request.app, snap, record_id)
    return JSONResponse({'status': 'accepted', 'record_id': record_id}, status_code=202)
