# coding: utf-8
"""Async SQLAlchemy 2.0 layer.

Three logical databases ("binds"): default (timer tasks), ``metadata`` and
``jobs``. One async engine per bind; a routing ``Session`` picks the engine by
each mapped class's ``__bind_key__`` so a single ``AsyncSession`` can touch all
three. Replaces Flask-SQLAlchemy.
"""
import re

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from .models import Base, Metadata
from .vars import SQLALCHEMY_BINDS, SQLALCHEMY_DATABASE_URI


def _to_async_url(url):
    if url.startswith('sqlite:///'):
        return url.replace('sqlite:///', 'sqlite+aiosqlite:///', 1)
    if url.startswith('mysql://'):
        return url.replace('mysql://', 'mysql+asyncmy://', 1)
    if url.startswith('postgres://'):
        return re.sub(r'^postgres://', 'postgresql+asyncpg://', url)
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    return url


def _engine_kwargs(url):
    # sqlite: no connection pool. The files can be recreated underneath a running
    # server (e.g. the test suite wipes *.db); a pooled connection would then point
    # at the old inode and every write fails with SQLITE_READONLY_DBMOVED
    # ("attempt to write a readonly database"). Opening by path per use is cheap.
    # postgres/mysql: pre-ping so connections killed by the test-mode
    # DROP DATABASE ... WITH (FORCE) are replaced instead of erroring.
    if url.startswith('sqlite'):
        return {'poolclass': NullPool}
    return {'pool_pre_ping': True}


# bind key -> async engine. None is the default bind.
engines = {
    None: create_async_engine(_to_async_url(SQLALCHEMY_DATABASE_URI), future=True,
                              **_engine_kwargs(SQLALCHEMY_DATABASE_URI)),
    'metadata': create_async_engine(_to_async_url(SQLALCHEMY_BINDS['metadata']), future=True,
                                    **_engine_kwargs(SQLALCHEMY_BINDS['metadata'])),
    'jobs': create_async_engine(_to_async_url(SQLALCHEMY_BINDS['jobs']), future=True,
                                **_engine_kwargs(SQLALCHEMY_BINDS['jobs'])),
}


def _bind_key_for(mapper):
    if mapper is not None:
        return getattr(mapper.class_, '__bind_key__', None)
    return None


class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None, **kw):
        key = _bind_key_for(mapper)
        if key is None and clause is not None and getattr(clause, 'table', None) is not None:
            key = clause.table.info.get('bind_key')
        return engines[key].sync_engine if key in engines else engines[None].sync_engine


SessionLocal = async_sessionmaker(
    bind=engines[None],
    sync_session_class=RoutingSession,
    expire_on_commit=False,
    autoflush=False,  # read-then-decorate loops mutate mapped cols for display; never auto-persist
)


def _tables_for_bind(bind_key):
    tables = []
    for mapper in Base.registry.mappers:
        if getattr(mapper.class_, '__bind_key__', None) == bind_key:
            tables.append(mapper.local_table)
    return tables


async def create_all_for_bind(bind_key):
    """Create the tables that belong to one bind on its engine."""
    tables = _tables_for_bind(bind_key)
    if not tables:
        return
    async with engines[bind_key].begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)


async def init_db():
    for bind_key in (None, 'metadata', 'jobs'):
        await create_all_for_bind(bind_key)


async def dispose_db():
    for engine in engines.values():
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
    """Fetch the row, self-healing if metadata.db was wiped under a live server."""
    try:
        return (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()
    except OperationalError:  # e.g. 'no such table: metadata' after the file was recreated
        await create_all_for_bind('metadata')
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
    """Get (and create) the per-server Job table model + physical table (jobs bind).

    The physical table is ensured on EVERY call (create_all is checkfirst /
    idempotent): the sqlite files can be wiped underneath a running server
    (e.g. the test suite deletes *.db), so a created-once cache would leave
    'no such table' errors behind.
    """
    if node in _jobs_tables:
        Job = _jobs_tables[node]
    else:
        Job = create_jobs_table(_re.sub(STRICT_NAME_PATTERN, '_', server))
        _jobs_tables[node] = Job
    await create_all_for_bind('jobs')
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
