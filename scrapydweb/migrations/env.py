# coding: utf-8
"""Alembic env: single database, URL derived from DATABASE_URL exactly like
the app does (scrapydweb.vars / setup_database).

The per-server Job tables are created at runtime by scrapydweb.db.get_jobs_table
and are NOT migration-managed: reflected tables unknown to the models are
ignored, never dropped. The APScheduler jobstore table is likewise ignored.
"""
from alembic import context
from sqlalchemy import create_engine

from scrapydweb.models import Base
from scrapydweb.vars import SQLALCHEMY_DATABASE_URI


def include_object(obj, name, type_, reflected, compare_to):
    # runtime tables (per-server job tables, apscheduler_jobs) are not migration-managed
    if type_ == 'table' and reflected and compare_to is None:
        return False
    return True


def run_migrations_online():
    engine = create_engine(SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit('offline (--sql) mode is not supported; run against a live database')
run_migrations_online()
