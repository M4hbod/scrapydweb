# coding: utf-8
"""DB-backed instance settings (the `setting` table on the metadata bind).

Values are stored json-encoded. The async accessors serve the API; the sync
loader runs inside create_app() (before the lifespan/init_db) to overlay
persisted settings onto the defaults.
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from .models import Setting

logger = logging.getLogger(__name__)


async def get_db_settings():
    from .db import SessionLocal, create_all_for_bind
    async with SessionLocal() as session:
        try:
            rows = (await session.execute(select(Setting))).scalars().all()
        except OperationalError:  # table wiped under a live server -- self-heal
            await create_all_for_bind('metadata')
            rows = (await session.execute(select(Setting))).scalars().all()
        return {r.key: json.loads(r.value) for r in rows}


async def set_db_settings(values):
    from .db import SessionLocal, create_all_for_bind
    await create_all_for_bind('metadata')
    async with SessionLocal() as session:
        for key, value in values.items():
            row = (await session.execute(select(Setting).filter_by(key=key))).scalar_one_or_none()
            if row is None:
                row = Setting(key=key)
                session.add(row)
            row.value = json.dumps(value)
        await session.commit()


async def delete_db_settings(keys):
    from .db import SessionLocal
    async with SessionLocal() as session:
        for key in keys:
            row = (await session.execute(select(Setting).filter_by(key=key))).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
        await session.commit()


def ensure_secret_sync():
    """Get-or-create the persisted SECRET_KEY (signs session cookies)."""
    import secrets as _secrets
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from .models import Base
    from .vars import SQLALCHEMY_BINDS

    try:
        engine = create_engine(SQLALCHEMY_BINDS['metadata'])
        try:
            Base.metadata.create_all(engine, tables=[Setting.__table__], checkfirst=True)
            s = sessionmaker(bind=engine)()
            try:
                row = s.query(Setting).filter_by(key='SECRET_KEY').first()
                if row is None:
                    row = Setting(key='SECRET_KEY', value=json.dumps(_secrets.token_hex(32)))
                    s.add(row)
                    s.commit()
                return json.loads(row.value)
            finally:
                s.close()
        finally:
            engine.dispose()
    except Exception as err:
        logger.warning('ensure_secret_sync failed (%s); using ephemeral secret', err)
        import secrets as _secrets2
        return _secrets2.token_hex(32)


def load_db_settings_sync():
    """Read all persisted settings with a throwaway sync engine.

    Used by create_app(), which runs before the async engines/lifespans exist.
    Returns {} on any failure (first boot, dropped DB) -- never crashes boot.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from .models import Base
    from .vars import SQLALCHEMY_BINDS

    try:
        engine = create_engine(SQLALCHEMY_BINDS['metadata'])
        try:
            Base.metadata.create_all(engine, tables=[Setting.__table__], checkfirst=True)
            s = sessionmaker(bind=engine)()
            try:
                rows = s.query(Setting).all()
                out = {}
                for r in rows:
                    try:
                        out[r.key] = json.loads(r.value)
                    except ValueError:
                        logger.warning('Dropping unreadable setting row %r', r.key)
                return out
            finally:
                s.close()
        finally:
            engine.dispose()
    except Exception as err:
        logger.warning('load_db_settings_sync failed (%s); using defaults', err)
        return {}
