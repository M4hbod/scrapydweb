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


# bind key -> async engine. None is the default bind.
engines = {
    None: create_async_engine(_to_async_url(SQLALCHEMY_DATABASE_URI), future=True),
    'metadata': create_async_engine(_to_async_url(SQLALCHEMY_BINDS['metadata']), future=True),
    'jobs': create_async_engine(_to_async_url(SQLALCHEMY_BINDS['jobs']), future=True),
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
    autoflush=True,
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

from .__version__ import __version__  # noqa: E402


async def get_metadata():
    async with SessionLocal() as session:
        row = (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()
        if not row:
            return {}
        return {k: v for k, v in row.__dict__.items() if not k.startswith('_')}


async def set_metadata(key, value):
    async with SessionLocal() as session:
        row = (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()
        if row is None:
            return
        setattr(row, key, value)
        await session.commit()


async def ensure_metadata_row():
    async with SessionLocal() as session:
        row = (await session.execute(
            select(Metadata).filter_by(version=__version__))).scalar_one_or_none()
        if row is None:
            session.add(Metadata(version=__version__))
            await session.commit()
