# coding: utf-8
"""GitHub webhook auto-deploy.

- /api/deploy/repos CRUD (session auth): register a git repo + branch + target
  nodes; a webhook secret is generated server-side.
- POST /api/webhooks/github/{repo_id}: GitHub push webhook. Authenticated by
  X-Hub-Signature-256 (HMAC-SHA256 of the raw body with the repo's secret) --
  the session middleware exempts this path (see app.py). The clone+build runs
  in BackgroundTasks (GitHub times webhooks out at 10s), so the endpoint
  answers 202 with a pending DeployRecord id.
"""
import hashlib
import hmac
import json
import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..db import SessionLocal
from ..models import DeployRepo

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_SOURCES = ('https://',)


def _repo_dict(repo):
    try:
        nodes = json.loads(repo.nodes_json)
    except ValueError:
        nodes = []
    return dict(
        id=repo.id, name=repo.name, repo_url=repo.repo_url, ref=repo.ref,
        project=repo.project, has_token=bool(repo.access_token),
        webhook_secret=repo.webhook_secret,
        webhook_path='/api/webhooks/github/%s' % repo.id,
        nodes=nodes, enabled=bool(repo.enabled),
        created_at=str(repo.created_at)[:19] if repo.created_at else None,
        updated_at=str(repo.updated_at)[:19] if repo.updated_at else None,
    )


def _validate(body, testing, partial=False):
    """Validate a create/update payload; returns (fields, error)."""
    fields = {}
    if 'name' in body or not partial:
        name = str(body.get('name') or '').strip()
        if not name:
            return None, 'name is required'
        fields['name'] = name
    if 'repo_url' in body or not partial:
        repo_url = str(body.get('repo_url') or '').strip()
        if not (repo_url.startswith('https://') or (testing and repo_url.startswith('file://'))):
            return None, 'repo_url must be an https:// URL'
        fields['repo_url'] = repo_url
    if 'project' in body or not partial:
        project = str(body.get('project') or '').strip()
        if not project:
            return None, 'project is required'
        fields['project'] = project
    if 'ref' in body or not partial:
        fields['ref'] = str(body.get('ref') or '').strip() or 'main'
    if 'access_token' in body:
        fields['access_token'] = str(body.get('access_token') or '').strip() or None
    if 'nodes' in body or not partial:
        raw = body.get('nodes') or [1]
        if not isinstance(raw, (list, tuple)):
            return None, 'nodes must be a list of node numbers'
        nodes = sorted({int(n) for n in raw if str(n).isdigit() and int(n) >= 1})
        if not nodes:
            return None, 'nodes must contain at least one node number'
        fields['nodes_json'] = json.dumps(nodes)
    if 'enabled' in body:
        fields['enabled'] = bool(body.get('enabled'))
    return fields, None


# ------------------------------------------------------------------ CRUD
@router.get('/api/deploy/repos', name='deploy.repos')
async def repos_list():
    async with SessionLocal() as s:
        rows = (await s.execute(select(DeployRepo).order_by(DeployRepo.id))).scalars().all()
        return JSONResponse({'status': 'ok', 'repos': [_repo_dict(r) for r in rows]})


@router.post('/api/deploy/repos', name='deploy.repos_create')
async def repos_create(request: Request):
    body = await request.json()
    testing = bool(request.app.state.settings.get('TESTING'))
    fields, err = _validate(body, testing)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        dup = (await s.execute(
            select(DeployRepo).filter_by(name=fields['name']))).scalar_one_or_none()
        if dup is not None:
            return JSONResponse({'status': 'error', 'message': 'a repo named %r already exists'
                                 % fields['name']}, status_code=400)
        repo = DeployRepo(webhook_secret=secrets.token_hex(32), **fields)
        s.add(repo)
        await s.commit()
        return JSONResponse({'status': 'ok', 'repo': _repo_dict(repo)})


@router.put('/api/deploy/repos/{repo_id:int}', name='deploy.repos_update')
async def repos_update(request: Request, repo_id: int):
    body = await request.json()
    testing = bool(request.app.state.settings.get('TESTING'))
    fields, err = _validate(body, testing, partial=True)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        repo = (await s.execute(select(DeployRepo).filter_by(id=repo_id))).scalar_one_or_none()
        if repo is None:
            return JSONResponse({'status': 'error', 'message': 'repo not found'}, status_code=404)
        for k, v in fields.items():
            setattr(repo, k, v)
        if body.get('rotate_secret'):
            repo.webhook_secret = secrets.token_hex(32)
        await s.commit()
        return JSONResponse({'status': 'ok', 'repo': _repo_dict(repo)})


@router.delete('/api/deploy/repos/{repo_id:int}', name='deploy.repos_delete')
async def repos_delete(repo_id: int):
    async with SessionLocal() as s:
        repo = (await s.execute(select(DeployRepo).filter_by(id=repo_id))).scalar_one_or_none()
        if repo is None:
            return JSONResponse({'status': 'error', 'message': 'repo not found'}, status_code=404)
        await s.delete(repo)
        await s.commit()
    return JSONResponse({'status': 'ok'})


# ------------------------------------------------------------------ webhook
async def _run_webhook_deploy(app, repo, record_id):
    """Background: clone, build, deploy to the repo's nodes, finalize the record."""
    from .deploy import deploy_egg_to_nodes, finish_deploy_record
    from .deploy_ci import _clone_and_build

    testing = bool(app.state.settings.get('TESTING'))
    try:
        built = await run_in_threadpool(
            _clone_and_build, repo['repo_url'], repo['ref'], repo['access_token'],
            repo['project'], '', testing)  # version '' -> short commit SHA
        if built.get('status') != 'built':
            await finish_deploy_record(record_id, 'error', message=built.get('message', ''))
            return
        overall, results, _first_js = await deploy_egg_to_nodes(
            app, repo['nodes'], built['project'], built['version'],
            built['egg_bytes'], built['eggname'])
        await finish_deploy_record(record_id, overall, results=results,
                                   version=built['version'], eggname=built['eggname'])
    except Exception as err:
        logger.exception('webhook deploy for repo %r failed', repo['name'])
        await finish_deploy_record(record_id, 'error', message=str(err))


@router.post('/api/webhooks/github/{repo_id:int}', name='webhooks.github')
async def github_webhook(request: Request, repo_id: int, background_tasks: BackgroundTasks):
    raw = await request.body()
    async with SessionLocal() as s:
        repo = (await s.execute(select(DeployRepo).filter_by(id=repo_id))).scalar_one_or_none()
        if repo is None or not repo.enabled:
            return JSONResponse({'status': 'error', 'message': 'unknown repo'}, status_code=404)
        snapshot = dict(name=repo.name, repo_url=repo.repo_url, ref=repo.ref,
                        project=repo.project, access_token=repo.access_token,
                        nodes=json.loads(repo.nodes_json or '[1]'),
                        webhook_secret=repo.webhook_secret)

    expected = 'sha256=' + hmac.new(snapshot['webhook_secret'].encode('utf-8'),
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
    if ref and ref != 'refs/heads/%s' % snapshot['ref']:
        return JSONResponse({'status': 'ok', 'message': 'ignored ref %r (deploying %r)'
                             % (ref, snapshot['ref'])})

    from .deploy import record_deploy
    record_id = await record_deploy('webhook', snapshot['project'], None, None, 'pending',
                                    actor='webhook:%s' % snapshot['name'],
                                    repo_id=repo_id)
    background_tasks.add_task(_run_webhook_deploy, request.app, snapshot, record_id)
    return JSONResponse({'status': 'accepted', 'record_id': record_id}, status_code=202)
