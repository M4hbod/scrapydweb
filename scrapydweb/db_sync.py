# coding: utf-8
"""Synchronous DB access for the background scheduler thread (execute_task).

The web app uses the async engine in scrapydweb.db; the APScheduler
BackgroundScheduler runs in its own thread (no asyncio loop), so its job
(execute_task) needs a plain sync session. Same models / database.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .vars import SQLALCHEMY_DATABASE_URI

# pre-ping -- see scrapydweb.db
sync_engine = create_engine(SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, autoflush=False)
