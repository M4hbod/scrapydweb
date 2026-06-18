# coding: utf-8
"""Personal access tokens for curl/API use (GitHub-PAT style).

Created by a logged-in user, the plaintext is returned once and only its sha256
is stored. Authenticate API calls with 'Authorization: Bearer sdw_...' (checked
in the app's session_auth middleware). This router itself is protected, so only
an authenticated session can mint or revoke tokens.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from ..auth import generate_api_token, hash_api_token
from ..db import SessionLocal
from ..models import ApiToken

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/tokens')


def token_dict(t):
    return dict(
        id=t.id, name=t.name, prefix=t.prefix,
        created_at=str(t.created_at)[:19] if t.created_at else None,
        last_used_at=str(t.last_used_at)[:19] if t.last_used_at else None,
    )


@router.get('', name='tokens.list')
async def tokens_list():
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(ApiToken).order_by(ApiToken.created_at.desc()))).scalars().all()
        return JSONResponse({'status': 'ok', 'tokens': [token_dict(t) for t in rows]})


@router.post('', name='tokens.create')
async def tokens_create(request: Request):
    body = await request.json()
    name = str(body.get('name') or '').strip()
    if not name:
        return JSONResponse({'status': 'error', 'message': 'name is required'}, status_code=400)
    raw = generate_api_token()
    t = ApiToken(name=name, token_hash=hash_api_token(raw), prefix=raw[:12] + '…')
    async with SessionLocal() as s:
        s.add(t)
        await s.commit()
        d = token_dict(t)
    # plaintext is returned exactly once -- it is never stored or shown again
    return JSONResponse({'status': 'ok', 'plaintext': raw, 'token': d})


@router.delete('/{token_id:int}', name='tokens.delete')
async def tokens_delete(token_id: int):
    async with SessionLocal() as s:
        t = (await s.execute(select(ApiToken).filter_by(id=token_id))).scalar_one_or_none()
        if t is None:
            return JSONResponse({'status': 'error', 'message': 'token not found'}, status_code=404)
        await s.delete(t)
        await s.commit()
    return JSONResponse({'status': 'ok'})
