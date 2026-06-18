# coding: utf-8
"""SQLAlchemy 2.0 models (async-ready).

One declarative ``Base``, one database. The per-server ``Job`` table is
created dynamically and cached (not migration-managed).
"""
from datetime import datetime
from pprint import pformat
import time

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, relationship

from .vars import STATE_RUNNING

# Postgres INTEGER is int32: ids/counters use BIGINT.
BigInt = BigInteger()


class Base(DeclarativeBase):
    pass


class User(Base):
    """Login account (single admin for now)."""
    __tablename__ = 'user'

    id = Column(BigInt, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return '<User %s>' % self.username


class JobStats(Base):
    """Centrally-collected per-job log stats (parsed by scrapydweb itself)."""
    __tablename__ = 'job_stats'
    __table_args__ = (UniqueConstraint('server', 'project', 'spider', 'job'),)

    id = Column(BigInt, primary_key=True)
    server = Column(String(255), nullable=False, index=True)  # '127.0.0.1:6800'
    project = Column(String(255), nullable=False)
    spider = Column(String(255), nullable=False)
    job = Column(String(255), nullable=False)                 # job id without log extension
    ext = Column(String(16), nullable=True)                   # discovered log extension
    size = Column(BigInteger, nullable=True)                  # last-seen HTTP byte size
    pages = Column(BigInt, nullable=True)
    items = Column(BigInt, nullable=True)
    runtime = Column(String(20), nullable=True)
    finish_reason = Column(String(64), nullable=True)         # 'N/A' while running
    first_log_time = Column(String(19), nullable=True)
    latest_log_time = Column(String(19), nullable=True)       # '%Y-%m-%d %H:%M:%S'
    stats_json = Column(Text(), nullable=True)                # json.dumps(logparser.parse(text))
    alert_state = Column(Text(), nullable=True)               # alert-engine dedup state (json)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return pformat(vars(self))


class Setting(Base):
    """One UI-editable instance setting: key + json-encoded value (metadata bind)."""
    __tablename__ = 'setting'

    key = Column(String(64), primary_key=True)
    value = Column(Text(), nullable=False)  # json.dumps(value)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return pformat(vars(self))


class Metadata(Base):
    __tablename__ = 'metadata'

    id = Column(BigInt, primary_key=True)
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


class Project(Base):
    """A registered project: its name is the identity, plus an optional saved
    deploy mechanism (folder/upload/git/webhook). Folds the old DeployRepo."""
    __tablename__ = 'project'

    id = Column(BigInt, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text(), nullable=True)
    deploy_source = Column(String(16), nullable=False, default='manual')  # manual|folder|git|webhook
    default_nodes_json = Column(Text(), nullable=False, default='[1]')    # json list of node numbers
    # git / webhook config (used when deploy_source is git or webhook)
    repo_url = Column(String(512), nullable=True)
    ref = Column(String(255), nullable=True, default='main')             # branch to deploy from
    access_token = Column(Text(), nullable=True)                         # private-repo clone token
    webhook_secret = Column(String(64), nullable=True)                   # HMAC secret (server-generated)
    enabled = Column(Boolean, nullable=False, default=True)              # webhook enabled
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return '<Project #%s %s (%s)>' % (self.id, self.name, self.deploy_source)


class JobGroup(Base):
    """A saved, reusable group of spiders to run together. Fired by id (like a
    timer task's 'fire now'), it schedules every spider on its nodes with the
    shared version/settings/arguments."""
    __tablename__ = 'job_group'

    id = Column(BigInt, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    project = Column(String(255), nullable=False)
    version = Column(String(255), nullable=True)          # None -> latest
    spiders_json = Column(Text(), nullable=False, default='[]')   # json list of spider names
    nodes_json = Column(Text(), nullable=False, default='[1]')    # json list of node numbers
    settings_json = Column(Text(), nullable=False, default='[]')  # json list of {key,value}
    args_json = Column(Text(), nullable=False, default='{}')      # json dict of spider args
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return '<JobGroup #%s %s>' % (self.id, self.name)


class DeployRecord(Base):
    """Audit log: one row per deploy attempt, whatever the entry point."""
    __tablename__ = 'deploy_record'

    id = Column(BigInt, primary_key=True)
    source = Column(String(16), nullable=False)         # file|folder|git|push|webhook
    project = Column(String(255), nullable=False)
    version = Column(String(255), nullable=True)
    eggname = Column(String(255), nullable=True)
    status = Column(String(8), nullable=False)          # pending|ok|partial|error
    actor = Column(String(255), nullable=True)          # username | 'deploy-token' | 'webhook:<name>'
    repo_id = Column(BigInt, nullable=True)             # DeployRepo.id for webhook deploys
    message = Column(Text(), nullable=True)             # error text / build output tail
    results_json = Column(Text(), nullable=True)        # [{node, server, status, status_code, message}]
    created_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return '<DeployRecord #%s %s %s/%s %s>' % (
            self.id, self.source, self.project, self.version, self.status)


class JobVersion(Base):
    """Which project version a scrapyd job was scheduled with (recorded at schedule time)."""
    __tablename__ = 'job_version'
    __table_args__ = (UniqueConstraint('server', 'project', 'job'),)

    id = Column(BigInt, primary_key=True)
    server = Column(String(255), nullable=False, index=True)  # '127.0.0.1:6800'
    project = Column(String(255), nullable=False)
    spider = Column(String(255), nullable=False)
    job = Column(String(255), nullable=False)                 # scrapyd jobid
    version = Column(String(255), nullable=False)
    source = Column(String(8), nullable=False, default='run')  # run|task
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return '<JobVersion %s %s/%s job=%s version=%s>' % (
            self.server, self.project, self.spider, self.job, self.version)


class AlertRule(Base):
    """Per-project/spider alert rule: non-null fields overlay the global settings."""
    __tablename__ = 'alert_rule'

    id = Column(BigInt, primary_key=True)
    name = Column(String(255), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    project_pattern = Column(String(255), nullable=False, default='*')  # fnmatch glob
    spider_pattern = Column(String(255), nullable=False, default='*')
    # {"CRITICAL": {"threshold": 5, "action": "stop"|"forcestop"|null}, ...}
    thresholds_json = Column(Text(), nullable=True)
    on_finished = Column(Boolean, nullable=True)            # null = inherit global
    on_running_interval = Column(Integer, nullable=True)    # seconds; null = inherit
    channels_json = Column(Text(), nullable=True)           # ["slack","email"]; null = inherit
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return '<AlertRule #%s %s %s/%s>' % (
            self.id, self.name, self.project_pattern, self.spider_pattern)


_jobs_table_cache = {}


def create_jobs_table(server):
    """Return (and cache) a dynamically-defined Job model bound to one server table."""
    if server in _jobs_table_cache:
        return _jobs_table_cache[server]

    class Job(Base):
        __tablename__ = server
        __table_args__ = (UniqueConstraint('project', 'spider', 'job'), {'extend_existing': True})

        id = Column(BigInt, primary_key=True)
        project = Column(String(255), unique=False, nullable=False)
        spider = Column(String(255), unique=False, nullable=False)
        job = Column(String(255), unique=False, nullable=False)
        status = Column(String(1), unique=False, nullable=False, index=True)  # Pending 0, Running 1, Finished 2
        deleted = Column(String(1), unique=False, nullable=False, default='0', index=True)
        create_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)
        update_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)

        pages = Column(BigInt, unique=False, nullable=True)
        items = Column(BigInt, unique=False, nullable=True)
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

    id = Column(BigInt, primary_key=True)
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

    id = Column(BigInt, primary_key=True)
    task_id = Column(BigInt, ForeignKey('task.id'), nullable=False, index=True)
    execute_time = Column(DateTime, unique=False, nullable=False, default=datetime.now)
    fail_count = Column(Integer, unique=False, nullable=False, default=0)
    pass_count = Column(Integer, unique=False, nullable=False, default=0)

    results = relationship('TaskJobResult', backref='task_result', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return "<TaskResult #%s of task #%s (%s), [FAIL %s, PASS %s], executed at %s>" % (
                self.id, self.task_id, self.task.name, self.fail_count, self.pass_count, self.execute_time)


class TaskJobResult(Base):
    __tablename__ = 'task_job_result'

    id = Column(BigInt, primary_key=True)
    task_result_id = Column(BigInt, ForeignKey('task_result.id'), nullable=False, index=True)
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
