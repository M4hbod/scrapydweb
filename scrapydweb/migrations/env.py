# coding: utf-8
"""Multi-database alembic env: one engine per bind, each database carries its
own alembic_version table. URLs are derived from DATABASE_URL exactly like the
app does (scrapydweb.vars / setup_database).

The per-server Job tables (jobs bind) are created at runtime by
scrapydweb.db.get_jobs_table and are NOT migration-managed: reflected tables
unknown to the models are ignored, never dropped.
"""
from alembic import context
from sqlalchemy import create_engine

from scrapydweb.models import Base
from scrapydweb.vars import SQLALCHEMY_BINDS, SQLALCHEMY_DATABASE_URI

config = context.config

# engine name -> (url, bind key in scrapydweb.db)
DATABASES = {
    'timer_tasks': (SQLALCHEMY_DATABASE_URI, None),
    'metadata': (SQLALCHEMY_BINDS['metadata'], 'metadata'),
    'jobs': (SQLALCHEMY_BINDS['jobs'], 'jobs'),
}


def _tables_for_bind(bind_key):
    return {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if getattr(mapper.class_, '__bind_key__', None) == bind_key
    }


def _make_include_object(table_names):
    def include_object(obj, name, type_, reflected, compare_to):
        if type_ == 'table':
            # runtime tables (per-server job tables) are not migration-managed
            if reflected and compare_to is None:
                return False
            return name in table_names
        return True

    return include_object


def run_migrations_online():
    for engine_name, (url, bind_key) in DATABASES.items():
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                upgrade_token='%s_upgrades' % engine_name,
                downgrade_token='%s_downgrades' % engine_name,
                include_object=_make_include_object(_tables_for_bind(bind_key)),
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations(engine_name=engine_name)
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit('offline (--sql) mode is not supported; run against live databases')
run_migrations_online()
