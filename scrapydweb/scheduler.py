# coding: utf-8
"""Timer-task scheduler (AsyncIOScheduler).

Replaces the Flask-coupled utils/scheduler.py. Runs on the app event loop; jobs
are async coroutines (see services/tasks.py, wired in Phase 4). Job metadata is
persisted via a (sync) SQLAlchemy jobstore, independent of the app's async ORM
engines.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from .vars import APSCHEDULER_DATABASE_URI

jobstores = {
    'default': SQLAlchemyJobStore(url=APSCHEDULER_DATABASE_URI),
    'memory': MemoryJobStore(),
}

scheduler = AsyncIOScheduler(jobstores=jobstores)


def safe_get_jobs(jobstore='default'):
    try:
        return scheduler.get_jobs(jobstore=jobstore)
    except Exception:
        return []
