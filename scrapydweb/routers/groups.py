# coding: utf-8
"""Saved spider groups: a reusable set of spiders run together.

A JobGroup is a name + project/version + a list of spiders, nodes, shared
settings and arguments. `POST /api/groups/{id}/fire` schedules every spider on
its nodes right now -- the curl equivalent of the timer task's "fire now",
addressable by id.
"""
import json
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from ..common import get_now_string
from ..context import DEFAULT_LATEST_VERSION
from ..db import SessionLocal
from ..models import JobGroup
from ..vars import LEGAL_NAME_PATTERN

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/groups')


def group_dict(g):
    def _load(s, default):
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return default
    return dict(
        id=g.id, name=g.name, project=g.project, version=g.version or '',
        spiders=_load(g.spiders_json, []), nodes=_load(g.nodes_json, [1]),
        settings=_load(g.settings_json, []), args=_load(g.args_json, {}),
        fire_path='/api/groups/%s/fire' % g.id,
        created_at=str(g.created_at)[:19] if g.created_at else None,
        updated_at=str(g.updated_at)[:19] if g.updated_at else None,
    )


def _validate(body, partial=False):
    fields = {}
    if 'name' in body or not partial:
        name = str(body.get('name') or '').strip()
        if not name:
            return None, 'name is required'
        fields['name'] = name
    if 'project' in body or not partial:
        project = str(body.get('project') or '').strip()
        if not project:
            return None, 'project is required'
        fields['project'] = project
    if 'version' in body:
        v = str(body.get('version') or '').strip()
        fields['version'] = v or None
    if 'spiders' in body or not partial:
        raw = body.get('spiders') or []
        if not isinstance(raw, (list, tuple)) or not raw:
            return None, 'spiders must be a non-empty list'
        fields['spiders_json'] = json.dumps([str(s) for s in raw if str(s).strip()])
    if 'nodes' in body or not partial:
        raw = body.get('nodes') or [1]
        nodes = sorted({int(n) for n in raw if str(n).isdigit() and int(n) >= 1})
        fields['nodes_json'] = json.dumps(nodes or [1])
    if 'settings' in body:
        raw = body.get('settings') or []
        fields['settings_json'] = json.dumps(
            [{'key': str(s.get('key', '')), 'value': str(s.get('value', ''))}
             for s in raw if isinstance(s, dict) and s.get('key') and s.get('value')])
    if 'args' in body:
        raw = body.get('args') or {}
        fields['args_json'] = json.dumps(
            {str(k): str(v) for k, v in raw.items()
             if re.match(r'^[a-zA-Z_][0-9a-zA-Z_]*$', str(k))})
    return fields, None


@router.get('', name='groups.list')
async def groups_list():
    async with SessionLocal() as s:
        rows = (await s.execute(select(JobGroup).order_by(JobGroup.name))).scalars().all()
        return JSONResponse({'status': 'ok', 'groups': [group_dict(g) for g in rows]})


@router.post('', name='groups.create')
async def groups_create(request: Request):
    body = await request.json()
    fields, err = _validate(body)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        dup = (await s.execute(select(JobGroup).filter_by(name=fields['name']))).scalar_one_or_none()
        if dup is not None:
            return JSONResponse({'status': 'error', 'message': 'group %r already exists'
                                 % fields['name']}, status_code=400)
        g = JobGroup(**fields)
        s.add(g)
        await s.commit()
        return JSONResponse({'status': 'ok', 'group': group_dict(g)})


@router.put('/{group_id:int}', name='groups.update')
async def groups_update(request: Request, group_id: int):
    body = await request.json()
    fields, err = _validate(body, partial=True)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        g = (await s.execute(select(JobGroup).filter_by(id=group_id))).scalar_one_or_none()
        if g is None:
            return JSONResponse({'status': 'error', 'message': 'group not found'}, status_code=404)
        if 'name' in fields and fields['name'] != g.name:
            dup = (await s.execute(
                select(JobGroup).filter_by(name=fields['name']))).scalar_one_or_none()
            if dup is not None:
                return JSONResponse({'status': 'error', 'message': 'group %r already exists'
                                     % fields['name']}, status_code=400)
        for k, v in fields.items():
            setattr(g, k, v)
        await s.commit()
        return JSONResponse({'status': 'ok', 'group': group_dict(g)})


@router.delete('/{group_id:int}', name='groups.delete')
async def groups_delete(group_id: int):
    async with SessionLocal() as s:
        g = (await s.execute(select(JobGroup).filter_by(id=group_id))).scalar_one_or_none()
        if g is None:
            return JSONResponse({'status': 'error', 'message': 'group not found'}, status_code=404)
        await s.delete(g)
        await s.commit()
    return JSONResponse({'status': 'ok'})


@router.post('/{group_id:int}/fire', name='groups.fire')
async def groups_fire(request: Request, group_id: int):
    """Run every spider in the group right now (the curl-by-id 'fire')."""
    from .schedule import run_group_now

    async with SessionLocal() as s:
        g = (await s.execute(select(JobGroup).filter_by(id=group_id))).scalar_one_or_none()
        if g is None:
            return JSONResponse({'status': 'error', 'message': 'group not found'}, status_code=404)
        snap = group_dict(g)

    app = request.app
    settings = app.state.settings
    servers = settings.get('SCRAPYD_SERVERS', []) or []
    auths = settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None] * len(servers)
    setting_list = ['%s=%s' % (s['key'], s['value']) for s in snap['settings']]
    extra_args = {str(k): str(v) for k, v in snap['args'].items()}
    base = re.sub(LEGAL_NAME_PATTERN, '-', '%s_%s' % (snap['name'], get_now_string()))
    results = await run_group_now(
        app, servers, auths, snap['project'], snap['version'] or DEFAULT_LATEST_VERSION,
        snap['spiders'], snap['nodes'], setting_list, extra_args, base)
    scheduled = sum(1 for r in results if r['status'] == 'ok')
    return JSONResponse(dict(status='ok', scheduled=scheduled, total=len(results), results=results))
