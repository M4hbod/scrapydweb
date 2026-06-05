# coding: utf-8
"""SQLAlchemy 2.0 models (async-ready).

One declarative ``Base`` shared by three logical databases ("binds"): the
default (timer tasks), ``metadata`` and ``jobs``. Each model carries a
``__bind_key__``; ``scrapydweb.db`` routes sessions/engines accordingly. The
per-server ``Job`` table is created dynamically and cached.
"""
from datetime import datetime
from pprint import pformat
import time

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, relationship

from .vars import STATE_RUNNING


class Base(DeclarativeBase):
    pass


class Metadata(Base):
    __tablename__ = 'metadata'
    __bind_key__ = 'metadata'

    id = Column(Integer, primary_key=True)
    version = Column(String(20), unique=True, nullable=False)
    last_check_update_timestamp = Column(Float, unique=False, default=time.time)
    main_pid = Column(Integer, unique=False, nullable=True)
    logparser_pid = Column(Integer, unique=False, nullable=True)
    poll_pid = Column(Integer, unique=False, nullable=True)
    pageview = Column(Integer, unique=False, nullable=False, default=0)
    url_scrapydweb = Column(Text(), unique=False, nullable=False, default='http://127.0.0.1:5000')
    url_jobs = Column(String(255), unique=False, nullable=False, default='/1/jobs/')
    url_schedule_task = Column(String(255), unique=False, nullable=False, default='/1/schedule/task/')
    url_delete_task_result = Column(String(255), unique=False, nullable=False, default='/1/tasks/xhr/delete/1/1/')
    username = Column(String(255), unique=False, nullable=True)
    password = Column(String(255), unique=False, nullable=True)
    scheduler_state = Column(Integer, unique=False, nullable=False, default=STATE_RUNNING)
    jobs_per_page = Column(Integer, unique=False, nullable=False, default=100)
    tasks_per_page = Column(Integer, unique=False, nullable=False, default=100)
    jobs_style = Column(String(8), unique=False, nullable=False, default='database')  # 'classic'

    def __repr__(self):
        return pformat(vars(self))


_jobs_table_cache = {}


def create_jobs_table(server):
    """Return (and cache) a dynamically-defined Job model bound to one server table."""
    if server in _jobs_table_cache:
        return _jobs_table_cache[server]

    class Job(Base):
        __tablename__ = server
        __bind_key__ = 'jobs'
        __table_args__ = (UniqueConstraint('project', 'spider', 'job'), {'extend_existing': True})

        id = Column(Integer, primary_key=True)
        project = Column(String(255), unique=False, nullable=False)
        spider = Column(String(255), unique=False, nullable=False)
        job = Column(String(255), unique=False, nullable=False)
        status = Column(String(1), unique=False, nullable=False, index=True)  # Pending 0, Running 1, Finished 2
        deleted = Column(String(1), unique=False, nullable=False, default='0', index=True)
        create_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)
        update_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)

        pages = Column(Integer, unique=False, nullable=True)
        items = Column(Integer, unique=False, nullable=True)
        pid = Column(Integer, unique=False, nullable=True)
        start = Column(DateTime, unique=False, nullable=True, index=True)
        runtime = Column(String(20), unique=False, nullable=True)
        finish = Column(DateTime, unique=False, nullable=True, index=True)
        href_log = Column(Text(), unique=False, nullable=True)
        href_items = Column(Text(), unique=False, nullable=True)

        def __repr__(self):
            return "<Job #%s in table %s, %s/%s/%s start: %s>" % (
                self.id, self.__tablename__, self.project, self.spider, self.job, self.start)

    _jobs_table_cache[server] = Job
    return Job


class Task(Base):
    __tablename__ = 'task'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=False, nullable=True)
    trigger = Column(String(8), unique=False, nullable=False)  # cron, interval, date
    create_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)
    update_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)

    project = Column(String(255), unique=False, nullable=False)
    version = Column(String(255), unique=False, nullable=False)
    spider = Column(String(255), unique=False, nullable=False)
    jobid = Column(String(255), unique=False, nullable=False)
    settings_arguments = Column(Text(), unique=False, nullable=False)
    selected_nodes = Column(Text(), unique=False, nullable=False)

    year = Column(String(255), unique=False, nullable=False)
    month = Column(String(255), unique=False, nullable=False)
    day = Column(String(255), unique=False, nullable=False)
    week = Column(String(255), unique=False, nullable=False)
    day_of_week = Column(String(255), unique=False, nullable=False)
    hour = Column(String(255), unique=False, nullable=False)
    minute = Column(String(255), unique=False, nullable=False)
    second = Column(String(255), unique=False, nullable=False)

    start_date = Column(String(19), unique=False, nullable=True)
    end_date = Column(String(19), unique=False, nullable=True)

    timezone = Column(String(255), unique=False, nullable=True)
    jitter = Column(Integer, unique=False, nullable=False)
    misfire_grace_time = Column(Integer, unique=False, nullable=True)
    coalesce = Column(String(5), unique=False, nullable=False)
    max_instances = Column(Integer, unique=False, nullable=False)

    results = relationship('TaskResult', backref='task', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return "<Task #%s (%s), %s/%s/%s/%s, created at %s, updated at %s>" % (
                self.id, self.name, self.project, self.version, self.spider, self.jobid,
                self.create_time, self.update_time)


class TaskResult(Base):
    __tablename__ = 'task_result'

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('task.id'), nullable=False, index=True)
    execute_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)
    fail_count = Column(Integer, unique=False, nullable=False, default=0)
    pass_count = Column(Integer, unique=False, nullable=False, default=0)

    results = relationship('TaskJobResult', backref='task_result', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return "<TaskResult #%s of task #%s (%s), [FAIL %s, PASS %s], executed at %s>" % (
                self.id, self.task_id, self.task.name, self.fail_count, self.pass_count, self.execute_time)


class TaskJobResult(Base):
    __tablename__ = 'task_job_result'

    id = Column(Integer, primary_key=True)
    task_result_id = Column(Integer, ForeignKey('task_result.id'), nullable=False, index=True)
    run_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)
    node = Column(Integer, unique=False, nullable=False, index=True)
    server = Column(String(255), unique=False, nullable=False)  # '127.0.0.1:6800'
    status_code = Column(Integer, unique=False, nullable=False)  # -1, 200
    status = Column(String(9), unique=False, nullable=False)  # ok|error|exception
    result = Column(Text(), unique=False, nullable=False)  # jobid|message|exception

    def __repr__(self):
        kwargs = dict(
            task_id=self.task_result.task_id,
            task_name=self.task_result.task.name,
            project=self.task_result.task.project,
            version=self.task_result.task.version,
            spider=self.task_result.task.spider,
            jobid=self.task_result.task.jobid,
            run_time=str(self.run_time),
            node=self.node,
            server=self.server,
            status_code=self.status_code,
            status=self.status,
            result=self.result,
            task_result_id=self.task_result_id,
            id=self.id,
        )
        return '<TaskJobResult \n%s>' % pformat(kwargs, indent=4)
