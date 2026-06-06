# coding: utf-8
"""Session auth endpoints: first-run setup, login, logout, me, change password."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from ..auth import (SESSION_COOKIE, SESSION_TTL, create_session_token,
                    hash_password, verify_password, verify_session_token)
from ..db import SessionLocal, create_all_for_bind
from ..models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/auth')


async def _user_count():
    async with SessionLocal() as s:
        try:
            return (await s.execute(select(func.count()).select_from(User))).scalar() or 0
        except Exception:
            await create_all_for_bind('metadata')
            return (await s.execute(select(func.count()).select_from(User))).scalar() or 0


async def _get_user(**filters):
    async with SessionLocal() as s:
        return (await s.execute(select(User).filter_by(**filters))).scalar_one_or_none()


def current_user_id(request):
    token = request.cookies.get(SESSION_COOKIE, '')
    if not token:
        return None
    return verify_session_token(token, request.app.state.settings['SECRET_KEY'])


def _login_response(payload, user, secret):
    resp = JSONResponse(payload)
    resp.set_cookie(SESSION_COOKIE, create_session_token(user.id, secret),
                    max_age=SESSION_TTL, httponly=True, samesite='lax', path='/')
    return resp


@router.get('/me', name='auth.me')
async def me(request: Request):
    setup_required = (await _user_count()) == 0
    user_id = current_user_id(request)
    user = await _get_user(id=user_id) if user_id is not None else None
    return JSONResponse(dict(
        authenticated=user is not None,
        username=user.username if user else None,
        setup_required=setup_required,
    ))


@router.post('/setup', name='auth.setup')
async def setup(request: Request):
    if (await _user_count()) > 0:
        return JSONResponse({'status': 'error', 'message': 'setup already completed'},
                            status_code=403)
    body = await request.json()
    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    if not username or len(password) < 8:
        return JSONResponse({'status': 'error',
                             'message': 'username required; password must be at least 8 characters'},
                            status_code=400)
    await create_all_for_bind('metadata')
    async with SessionLocal() as s:
        user = User(username=username, password_hash=hash_password(password))
        s.add(user)
        await s.commit()
        await s.refresh(user)
    logger.info('Admin account %r created', username)
    return _login_response({'status': 'ok', 'username': username}, user,
                           request.app.state.settings['SECRET_KEY'])


@router.post('/login', name='auth.login')
async def login(request: Request):
    body = await request.json()
    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    user = await _get_user(username=username)
    if user is None or not verify_password(password, user.password_hash):
        return JSONResponse({'status': 'error', 'message': 'invalid username or password'},
                            status_code=401)
    return _login_response({'status': 'ok', 'username': user.username}, user,
                           request.app.state.settings['SECRET_KEY'])


@router.post('/logout', name='auth.logout')
async def logout():
    resp = JSONResponse({'status': 'ok'})
    resp.delete_cookie(SESSION_COOKIE, path='/')
    return resp


@router.post('/password', name='auth.password')
async def change_password(request: Request):
    user_id = current_user_id(request)
    user = await _get_user(id=user_id) if user_id is not None else None
    if user is None:
        return JSONResponse({'status': 'error', 'message': 'unauthenticated'}, status_code=401)
    body = await request.json()
    current = str(body.get('current') or '')
    new = str(body.get('new') or '')
    if not verify_password(current, user.password_hash):
        return JSONResponse({'status': 'error', 'message': 'current password is wrong'},
                            status_code=400)
    if len(new) < 8:
        return JSONResponse({'status': 'error', 'message': 'new password must be at least 8 characters'},
                            status_code=400)
    async with SessionLocal() as s:
        row = (await s.execute(select(User).filter_by(id=user.id))).scalar_one()
        row.password_hash = hash_password(new)
        await s.commit()
    return JSONResponse({'status': 'ok'})
