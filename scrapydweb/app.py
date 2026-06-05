# coding: utf-8
"""FastAPI application factory.

Replaces the Flask ``create_app``/``handle_*`` machinery in the old
``__init__.py``. The app is fully async; settings live on ``app.state.settings``
(see ``scrapydweb.settings``) and routers are included from
``scrapydweb.routers``.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .db import dispose_db, ensure_metadata_row, get_metadata, init_db, set_metadata
from .settings import build_settings
from .vars import ROOT_DIR

logger = logging.getLogger(__name__)

STATIC_DIR = ROOT_DIR + '/static'


@asynccontextmanager
async def lifespan(app):
    await init_db()
    await ensure_metadata_row()
    meta = await get_metadata()
    if time.time() - meta.get('last_check_update_timestamp', time.time()) > 3600 * 24 * 30:
        await set_metadata('last_check_update_timestamp', time.time())
        await set_metadata('pageview', 0)
    else:
        await set_metadata('pageview', 1)
    yield
    await dispose_db()


def create_app(test_config=None):
    settings = build_settings(test_config)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.context_processors = []
    # Convenience aliases (mirror the old Flask app surface used by tests/helpers).
    app.config = settings  # same mutable mapping the deps read
    app.testing = bool(settings.get('TESTING'))

    app.add_middleware(GZipMiddleware, minimum_size=500)

    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/hello', response_class=PlainTextResponse)
    async def hello():
        return "Hello, World!"

    from .routers import register_routers
    register_routers(app)

    return app
