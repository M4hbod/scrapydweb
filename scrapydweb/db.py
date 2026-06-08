# coding: utf-8
"""Async SQLAlchemy 2.0 layer.

One database, one async engine. Schema is managed by alembic (run in
create_app()); ``ensure_tables`` keeps a checkfirst create_all around for
runtime-only tables (per-server job tables) and test-mode self-healing.
"""
import re

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .models import Base, Metadata
from .vars import SQLALCHEMY_DATABASE_URI


def _to_async_url(url):
    if url.startswith('mysql://'):
        return url.replace('mysql://', 'mysql+asyncmy://', 1)
    if url.startswith('postgres://'):
        return re.sub(r'^postgres://', 'postgresql+asyncpg://', url)
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    return url


# pre-ping so connections killed by the test-mode DROP DATABASE ... WITH (FORCE)
# are replaced instead of erroring.
engine = create_async_engine(_to_async_url(SQLALCHEMY_DATABASE_URI), future=True,
                             pool_pre_ping=True)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,  # read-then-decorate loops mutate mapped cols for display; never auto-persist
)


async def ensure_tables():
    """checkfirst create_all: runtime tables (per-server job tables) + self-heal."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run_db_migrations():
    """alembic upgrade head (sync; runs in create_app before anything reads the DB)."""
    import os

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option('script_location', os.path.join(os.path.dirname(__file__), 'migrations'))
    command.upgrade(cfg, 'head')


async def init_db():
    # Migrations already ran synchronously in create_app(); see ensure_tables.
    await ensure_tables()


async def dispose_db():
    await engine.dispose()


# https://fastapi.tiangolo.com/tutorial/sql-databases/  dependency
async def get_session():
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ------------------------------------------------------------------ metadata
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from .__version__ import __version__  # noqa: E402


async def _metadata_row(session):
    """Fetch the row, self-healing if the database was recreated under a live server."""
    try:
        return (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()
    except OperationalError:  # e.g. 'no such table' after a test-mode drop
        await ensure_tables()
        await ensure_metadata_row()
        return (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()


async def get_metadata():
    async with SessionLocal() as session:
        row = await _metadata_row(session)
        if not row:
            return {}
        return {k: v for k, v in row.__dict__.items() if not k.startswith('_')}


async def set_metadata(key, value):
    async with SessionLocal() as session:
        row = await _metadata_row(session)
        if row is None:
            return
        setattr(row, key, value)
        await session.commit()


import re as _re  # noqa: E402

from .models import create_jobs_table  # noqa: E402
from .vars import STRICT_NAME_PATTERN  # noqa: E402

_jobs_tables = {}


async def get_jobs_table(node, server):
    """Get (and create) the per-server Job table model + physical table.

    The physical table is ensured on EVERY call (create_all is checkfirst /
    idempotent): the database can be dropped underneath a running server
    (e.g. the test suite recreates it), so a created-once cache would leave
    'no such table' errors behind.
    """
    if node in _jobs_tables:
        Job = _jobs_tables[node]
    else:
        Job = create_jobs_table(_re.sub(STRICT_NAME_PATTERN, '_', server))
        _jobs_tables[node] = Job
    await ensure_tables()
    return Job


def jobs_table_for(node):
    return _jobs_tables.get(node)


class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max(1, (total + per_page - 1) // per_page) if per_page else 1


async def ensure_metadata_row():
    async with SessionLocal() as session:
        row = (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()
        if row is None:
            session.add(Metadata(version=__version__))
            await session.commit()
