# coding: utf-8
"""Timer-task scheduler (AsyncIOScheduler) - replaces the Flask-coupled utils/scheduler.py.

Runs on the app event loop; the job function (services.tasks.execute_task) is an
async coroutine. Job metadata is persisted via a sync SQLAlchemy jobstore,
independent of the app's async ORM engines. Started in the app lifespan.
"""
import logging
from pprint import pformat

from apscheduler.events import EVENT_JOB_MAX_INSTANCES, EVENT_JOB_REMOVED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED

from .vars import SQLALCHEMY_DATABASE_URI, TIMER_TASKS_HISTORY_LOG

apscheduler_logger = logging.getLogger('apscheduler')
_handler = logging.FileHandler(TIMER_TASKS_HISTORY_LOG, mode='a', encoding='utf-8')
_handler.setLevel(logging.WARNING)
_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s] %(levelname)s in %(name)s: %(message)s"))
apscheduler_logger.addHandler(_handler)

EVENT_MAP = {EVENT_JOB_MAX_INSTANCES: 'EVENT_JOB_MAX_INSTANCES', EVENT_JOB_REMOVED: 'EVENT_JOB_REMOVED'}

jobstores = {
    'default': SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URI),
    'memory': MemoryJobStore(),
}
executors = {'default': ThreadPoolExecutor(20)}
job_defaults = {'coalesce': True, 'max_instances': 1}

# Thread-based: independent of the web app's asyncio loop, so timer jobs persist
# and fire across test client lifecycles (execute_task is a sync function).
scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults)

# Separate always-on scheduler for system/maintenance jobs (stats collector, jobs
# snapshot, task-result cleanup). Kept independent of `scheduler` so pausing timer
# tasks does NOT pause data freshness. Memory jobstore only.
system_scheduler = BackgroundScheduler(
    jobstores={'memory': MemoryJobStore()}, executors={'default': ThreadPoolExecutor(10)},
    job_defaults=job_defaults)


def _my_listener(event):
    msg = "%s: \n%s\n" % (EVENT_MAP[event.code], pformat(vars(event), indent=4))
    if event.jobstore != 'default':
        logging.getLogger('apscheduler').info(msg)
    else:
        logging.getLogger('apscheduler').warning(msg)


scheduler.add_listener(_my_listener, EVENT_JOB_MAX_INSTANCES | EVENT_JOB_REMOVED)


def safe_get_jobs(jobstore='default'):
    try:
        return scheduler.get_jobs(jobstore=jobstore)
    except Exception:
        return []
