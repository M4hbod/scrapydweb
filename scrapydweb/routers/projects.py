# coding: utf-8
"""Project registry + per-project deploy mechanism.

A Project is a name plus an optional saved deploy config (manual/folder/git/
webhook). The deploy page chooser and the Projects page are driven by these;
`POST /api/projects/{id}/deploy` runs a project's saved git/webhook mechanism
in one shot. Webhook auto-deploy config lives here too (folded from the old
DeployRepo); the GitHub push handler is in routers/webhooks.py, keyed by the
project id.
"""
import json
import logging
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from ..db import SessionLocal
from ..models import Project

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/projects')

VALID_SOURCES = ('manual', 'folder', 'git', 'webhook')


def project_dict(p):
    try:
        nodes = json.loads(p.default_nodes_json)
    except (ValueError, TypeError):
        nodes = [1]
    return dict(
        id=p.id, name=p.name, description=p.description or '',
        deploy_source=p.deploy_source, default_nodes=nodes,
        repo_url=p.repo_url or '', ref=p.ref or 'main',
        has_token=bool(p.access_token), enabled=bool(p.enabled),
        webhook_secret=p.webhook_secret,
        webhook_path=('/api/webhooks/github/%s' % p.id) if p.webhook_secret else None,
        created_at=str(p.created_at)[:19] if p.created_at else None,
        updated_at=str(p.updated_at)[:19] if p.updated_at else None,
    )


def _validate(body, testing, partial=False):
    """Validate a create/update payload; returns (fields, error)."""
    fields = {}
    if 'name' in body or not partial:
        name = str(body.get('name') or '').strip()
        if not name:
            return None, 'name is required'
        fields['name'] = name
    if 'description' in body:
        fields['description'] = str(body.get('description') or '').strip() or None
    source = None
    if 'deploy_source' in body or not partial:
        source = str(body.get('deploy_source') or 'manual').strip() or 'manual'
        if source not in VALID_SOURCES:
            return None, 'deploy_source must be one of %s' % (VALID_SOURCES,)
        fields['deploy_source'] = source
    if 'nodes' in body or not partial:
        raw = body.get('nodes') or [1]
        if not isinstance(raw, (list, tuple)):
            return None, 'nodes must be a list of node numbers'
        nodes = sorted({int(n) for n in raw if str(n).isdigit() and int(n) >= 1})
        fields['default_nodes_json'] = json.dumps(nodes or [1])
    if 'repo_url' in body or (source in ('git', 'webhook')):
        repo_url = str(body.get('repo_url') or '').strip()
        if source in ('git', 'webhook') and not (
                repo_url.startswith('https://') or (testing and repo_url.startswith('file://'))):
            return None, 'a %s project needs an https:// repo_url' % source
        if repo_url and not (repo_url.startswith('https://') or (testing and repo_url.startswith('file://'))):
            return None, 'repo_url must be an https:// URL'
        fields['repo_url'] = repo_url or None
    if 'ref' in body or not partial:
        fields['ref'] = str(body.get('ref') or '').strip() or 'main'
    if 'access_token' in body:
        fields['access_token'] = str(body.get('access_token') or '').strip() or None
    if 'enabled' in body:
        fields['enabled'] = bool(body.get('enabled'))
    return fields, None


@router.get('', name='projects.list')
async def projects_list():
    async with SessionLocal() as s:
        rows = (await s.execute(select(Project).order_by(Project.name))).scalars().all()
        return JSONResponse({'status': 'ok', 'projects': [project_dict(p) for p in rows]})


@router.post('', name='projects.create')
async def projects_create(request: Request):
    body = await request.json()
    testing = bool(request.app.state.settings.get('TESTING'))
    fields, err = _validate(body, testing)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        dup = (await s.execute(
            select(Project).filter_by(name=fields['name']))).scalar_one_or_none()
        if dup is not None:
            return JSONResponse({'status': 'error', 'message': 'project %r already exists'
                                 % fields['name']}, status_code=400)
        if fields.get('deploy_source') == 'webhook':
            fields['webhook_secret'] = secrets.token_hex(32)
        p = Project(**fields)
        s.add(p)
        await s.commit()
        return JSONResponse({'status': 'ok', 'project': project_dict(p)})


@router.put('/{project_id:int}', name='projects.update')
async def projects_update(request: Request, project_id: int):
    body = await request.json()
    testing = bool(request.app.state.settings.get('TESTING'))
    fields, err = _validate(body, testing, partial=True)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        p = (await s.execute(select(Project).filter_by(id=project_id))).scalar_one_or_none()
        if p is None:
            return JSONResponse({'status': 'error', 'message': 'project not found'}, status_code=404)
        if 'name' in fields and fields['name'] != p.name:
            dup = (await s.execute(
                select(Project).filter_by(name=fields['name']))).scalar_one_or_none()
            if dup is not None:
                return JSONResponse({'status': 'error', 'message': 'project %r already exists'
                                     % fields['name']}, status_code=400)
        for k, v in fields.items():
            setattr(p, k, v)
        # a webhook project must have a secret; generate one if switching to it
        if (fields.get('deploy_source') == 'webhook' or body.get('rotate_secret')) and (
                body.get('rotate_secret') or not p.webhook_secret):
            p.webhook_secret = secrets.token_hex(32)
        await s.commit()
        return JSONResponse({'status': 'ok', 'project': project_dict(p)})


@router.delete('/{project_id:int}', name='projects.delete')
async def projects_delete(project_id: int):
    async with SessionLocal() as s:
        p = (await s.execute(select(Project).filter_by(id=project_id))).scalar_one_or_none()
        if p is None:
            return JSONResponse({'status': 'error', 'message': 'project not found'}, status_code=404)
        await s.delete(p)
        await s.commit()
    return JSONResponse({'status': 'ok'})


@router.post('/{project_id:int}/deploy', name='projects.deploy')
async def projects_deploy(request: Request, project_id: int):
    """Run the project's saved git/webhook mechanism: clone, build, deploy."""
    from .deploy import actor_from_request, deploy_egg_to_nodes, finish_deploy_record, record_deploy
    from .deploy_ci import _clone_and_build

    async with SessionLocal() as s:
        p = (await s.execute(select(Project).filter_by(id=project_id))).scalar_one_or_none()
        if p is None:
            return JSONResponse({'status': 'error', 'message': 'project not found'}, status_code=404)
        snap = dict(name=p.name, deploy_source=p.deploy_source, repo_url=p.repo_url,
                    ref=p.ref or 'main', access_token=p.access_token,
                    nodes=json.loads(p.default_nodes_json or '[1]'))

    if snap['deploy_source'] not in ('git', 'webhook') or not snap['repo_url']:
        return JSONResponse({'status': 'error',
                             'message': 'project has no git deploy configured'}, status_code=400)

    actor = await actor_from_request(request)
    testing = bool(request.app.state.settings.get('TESTING'))
    record_id = await record_deploy('git', snap['name'], None, None, 'pending', actor=actor)
    built = await run_in_threadpool(_clone_and_build, snap['repo_url'], snap['ref'],
                                    snap['access_token'], snap['name'], '', testing)
    if built.get('status') != 'built':
        await finish_deploy_record(record_id, 'error', message=built.get('message', ''))
        return JSONResponse({'status': 'error', 'message': built.get('message', 'build failed')},
                            status_code=400)
    overall, results, first_js = await deploy_egg_to_nodes(
        request.app, snap['nodes'], built['project'], built['version'],
        built['egg_bytes'], built['eggname'])
    await finish_deploy_record(record_id, overall, results=results,
                               version=built['version'], eggname=built['eggname'])
    status = 'error' if overall == 'error' else 'ok'
    return JSONResponse(dict(status=status, overall=overall, project=built['project'],
                             version=built['version'], eggname=built['eggname'],
                             results=results, record_id=record_id),
                        status_code=200 if status == 'ok' else 400)
