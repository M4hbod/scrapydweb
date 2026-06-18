# coding: utf-8
"""FastAPI application factory.

Replaces the Flask ``create_app``/``handle_*`` machinery in the old
``__init__.py``. The app is fully async; settings live on ``app.state.settings``
(see ``scrapydweb.settings``) and routers are included from
``scrapydweb.routers``.
"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .db import dispose_db, ensure_metadata_row, get_metadata, init_db, set_metadata
from .settings import build_settings
from .vars import ROOT_DIR

logger = logging.getLogger(__name__)

STATIC_DIR = ROOT_DIR + '/static'


@asynccontextmanager
async def lifespan(app):
    from .services.scrapyd import new_client
    from .services.tasks import set_app as set_tasks_app
    from .scheduler import scheduler
    from apscheduler.schedulers.base import STATE_RUNNING
    app.state.http_client = new_client()
    await init_db()
    await ensure_metadata_row()
    meta = await get_metadata()
    if time.time() - meta.get('last_check_update_timestamp', time.time()) > 3600 * 24 * 30:
        await set_metadata('last_check_update_timestamp', time.time())
        await set_metadata('pageview', 0)
    else:
        await set_metadata('pageview', 1)

    # seed the admin account from env USERNAME/PASSWORD (compose convenience)
    # when no user exists yet
    import os as _os
    if _os.environ.get('USERNAME') and _os.environ.get('PASSWORD'):
        from sqlalchemy import func as _f, select as _sel
        from .auth import hash_password
        from .db import SessionLocal as _SL
        from .models import User as _U
        async with _SL() as s:
            if not ((await s.execute(_sel(_f.count()).select_from(_U))).scalar() or 0):
                s.add(_U(username=_os.environ['USERNAME'],
                         password_hash=hash_password(_os.environ['PASSWORD'])))
                await s.commit()
                logger.info('Seeded admin account %r from env', _os.environ['USERNAME'])

    set_tasks_app(app)
    # BackgroundScheduler runs in its own thread; start once and keep it running
    # across app/test lifecycles (do not shut it down per request lifespan).
    if not scheduler.running:
        scheduler.start(paused=True)
        if meta.get('scheduler_state') == STATE_RUNNING:
            scheduler.resume()
    yield
    await app.state.http_client.aclose()
    await dispose_db()


def create_app(test_config=None):
    # Bring the databases to the current schema before anything reads them
    # (the settings overlay below touches the 'setting' table).
    from .db import _run_db_migrations
    _run_db_migrations()

    # Layered settings: defaults < env overlays < DB-persisted (UI edits) < test overrides.
    from .settings import env_overrides
    from .settings_registry import EXTRA_DB_KEYS, REGISTRY, coerce
    from .settings_store import load_db_settings_sync

    settings = build_settings()
    sources = {k: 'default' for k in settings}

    env_vals = env_overrides()
    settings.update(env_vals)
    sources.update({k: 'env' for k in env_vals})

    db_vals = {}
    for key, value in load_db_settings_sync().items():
        if key == 'SECRET_KEY':
            continue  # handled by ensure_secret_sync below
        if key in EXTRA_DB_KEYS:
            db_vals[key] = value
            continue
        field = REGISTRY.get(key)
        if field is None:
            logger.warning('Ignoring unknown persisted setting %r', key)
            continue
        coerced, err = coerce(field, value)
        if err:
            logger.warning('Dropping invalid persisted setting %s: %s', key, err)
            continue
        db_vals[key] = coerced
    settings.update(db_vals)
    sources.update({k: 'db' for k in db_vals})

    if test_config:
        settings.update(test_config)
        sources.update({k: 'test' for k in test_config})

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # DB URI lives in vars (module constant); expose on settings for the settings page / tests.
    from .vars import SQLALCHEMY_DATABASE_URI
    settings.setdefault('SQLALCHEMY_DATABASE_URI', SQLALCHEMY_DATABASE_URI)

    # derive SCRAPYD_SERVERS_* lists whenever pre-parsed lists were not injected
    # (conftest passes _AUTHS/_GROUPS explicitly). Covers env/db AND the
    # defaults: raw entries may be 'user:pass@host:port#group' strings or
    # legacy tuples, which every consumer (settings page, deploy, ...) would
    # otherwise trip over when booting via scrapydweb.asgi:app.
    if 'SCRAPYD_SERVERS_AUTHS' not in settings:
        # keep the raw authed strings: derivation strips credentials out of
        # SCRAPYD_SERVERS, and check_app_config re-derives from _SCRAPYD_SERVERS
        settings['_SCRAPYD_SERVERS'] = list(settings['SCRAPYD_SERVERS'])
        try:
            from .utils.check_app_config import check_scrapyd_servers
            check_scrapyd_servers(settings, check_connectivity=False)
        except Exception as err:
            logger.warning('SCRAPYD_SERVERS derivation failed: %s', err)

    # session-signing secret (persisted) + per-boot internal token for the
    # poll subprocess / apscheduler jobs that call our own HTTP endpoints
    import secrets as _secrets
    from .settings_store import ensure_secret_sync
    settings['SECRET_KEY'] = ensure_secret_sync()
    settings['_INTERNAL_TOKEN'] = _secrets.token_hex(32)

    app.state.settings = settings
    app.state.settings_sources = sources
    app.state.pending_restart = set()
    app.state.context_processors = []
    # Convenience aliases (mirror the old Flask app surface used by tests/helpers).
    app.config = settings  # same mutable mapping the deps read
    app.testing = bool(settings.get('TESTING'))

    def context_processor(func):
        app.state.context_processors.append(func)
        return func
    app.context_processor = context_processor

    app.add_middleware(GZipMiddleware, minimum_size=500)

    # node-scoped endpoints with no/invalid node: JSON 400, not a 500
    from .context import NodeIndexError

    @app.exception_handler(NodeIndexError)
    async def node_index_error(request, exc):
        from starlette.responses import JSONResponse as _JR
        return _JR({'status': 'error', 'message': str(exc),
                    'node': exc.node, 'servers_amount': exc.amount}, status_code=400)

    # Session auth. Protects the data surface (API + node-prefixed JSON
    # endpoints); the SPA shell + its assets stay public so the login page can
    # render. While no user exists (first run) everything is open and the SPA
    # shows the create-admin setup screen.
    import re as _re
    _PROTECTED = _re.compile(
        r'^(/api/(?!auth/)|/\d+/|/tasks/history/|/schedule/history/)')
    # GitHub webhook deliveries carry no session; the handler verifies the
    # per-repo HMAC signature (X-Hub-Signature-256) over the raw body itself.
    _WEBHOOK = _re.compile(r'^/api/webhooks/github/\d+$')

    @app.middleware('http')
    async def session_auth(request, call_next):
        path = request.url.path
        if _PROTECTED.match(path):
            from .auth import INTERNAL_TOKEN_HEADER, SESSION_COOKIE, verify_session_token
            st = request.app.state
            # internal callers (apscheduler system jobs)
            if request.headers.get(INTERNAL_TOKEN_HEADER, '') == st.settings.get('_INTERNAL_TOKEN'):
                return await call_next(request)
            # GitHub webhooks: HMAC-verified in the handler
            if request.method == 'POST' and _WEBHOOK.match(path):
                return await call_next(request)
            # CI deploys: static deploy token, valid ONLY for the push endpoint
            if path == '/api/deploy/push' and request.method == 'POST':
                import secrets as _sec
                configured = st.settings.get('DEPLOY_TOKEN') or ''
                supplied = request.headers.get('X-Deploy-Token', '')
                if configured and supplied and _sec.compare_digest(supplied, configured):
                    return await call_next(request)
            # Personal access token (curl/API): 'Authorization: Bearer sdw_...'
            authz = request.headers.get('Authorization', '')
            if authz.startswith('Bearer '):
                raw = authz[7:].strip()
                if raw and await _valid_api_token(raw):
                    return await call_next(request)
            token = request.cookies.get(SESSION_COOKIE, '')
            if verify_session_token(token, st.settings['SECRET_KEY']) is None:
                # first run (no admin yet): open -- the SPA forces the setup screen.
                # users_exist is cached once True (the admin cannot be deleted).
                if not getattr(st, 'users_exist', False):
                    st.users_exist = await _any_user()
                    if not st.users_exist:
                        return await call_next(request)
                from starlette.responses import JSONResponse as _JR
                return _JR({'status': 'error', 'error': 'unauthenticated'}, status_code=401)
        return await call_next(request)

    async def _any_user():
        from sqlalchemy import func as _f, select as _sel
        from .db import SessionLocal as _SL
        from .models import User as _U
        try:
            async with _SL() as s:
                n = (await s.execute(_sel(_f.count()).select_from(_U))).scalar() or 0
            return n > 0
        except Exception:
            return False

    async def _valid_api_token(raw):
        from datetime import datetime as _dt
        from sqlalchemy import select as _sel
        from .auth import hash_api_token
        from .db import SessionLocal as _SL
        from .models import ApiToken as _T
        try:
            async with _SL() as s:
                tok = (await s.execute(
                    _sel(_T).filter_by(token_hash=hash_api_token(raw)))).scalar_one_or_none()
                if tok is None:
                    return False
                tok.last_used_at = _dt.now()
                await s.commit()
            return True
        except Exception:
            return False

    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/hello', response_class=PlainTextResponse)
    async def hello():
        return "Hello, World!"

    from .routers import register_routers
    register_routers(app)

    # React SPA (frontend/dist). Mounted last: the catch-all only fires for
    # paths no API route matched, so /api, /static, the node-prefixed JSON
    # endpoints (/1/api/..., /1/tasks/xhr/...) and sendtext keep working.
    frontend_dist = os.environ.get(
        'FRONTEND_DIST', os.path.join(os.path.dirname(ROOT_DIR), 'frontend', 'dist'))
    index_html = os.path.join(frontend_dist, 'index.html')
    if os.path.isfile(index_html):
        assets_dir = os.path.join(frontend_dist, 'assets')
        if os.path.isdir(assets_dir):
            app.mount('/assets', StaticFiles(directory=assets_dir), name='spa-assets')

        @app.get('/{full_path:path}', include_in_schema=False)
        async def spa_fallback(full_path: str):
            file_path = os.path.join(frontend_dist, full_path)
            if full_path and os.path.isfile(file_path):
                return FileResponse(file_path)
            # never cache the shell: it references hashed bundles that change on
            # every deploy -- a cached index.html would point at dead assets
            return FileResponse(index_html, headers={'Cache-Control': 'no-cache'})
    else:
        logger.warning('frontend/dist not found (%s) - run `just ui-build`; SPA routes disabled',
                       frontend_dist)

    return app
