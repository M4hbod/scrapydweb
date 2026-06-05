# coding: utf-8
"""Synchronous DB access for the background scheduler thread (execute_task).

The web app uses the async engines in scrapydweb.db; the APScheduler
BackgroundScheduler runs in its own thread (no asyncio loop), so its job
(execute_task) needs a plain sync session. Same models / sqlite files.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .vars import SQLALCHEMY_BINDS, SQLALCHEMY_DATABASE_URI

sync_engines = {
    None: create_engine(SQLALCHEMY_DATABASE_URI),
    'metadata': create_engine(SQLALCHEMY_BINDS['metadata']),
    'jobs': create_engine(SQLALCHEMY_BINDS['jobs']),
}


class SyncRoutingSession(Session):
    def get_bind(self, mapper=None, clause=None, **kw):
        if mapper is not None:
            key = getattr(mapper.class_, '__bind_key__', None)
            if key in sync_engines:
                return sync_engines[key]
        return sync_engines[None]


SyncSessionLocal = sessionmaker(class_=SyncRoutingSession, expire_on_commit=False, autoflush=False)
