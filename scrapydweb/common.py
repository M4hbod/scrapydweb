# coding: utf-8
"""Framework-agnostic helpers (no web framework imports).

Flask-specific helpers that lived here (authenticate, get_response_from_view,
the requests Session, handle_metadata) are reimplemented in the async
services/deps during the FastAPI migration.
"""
import json
import os
import time
import traceback

import requests
from requests.adapters import HTTPAdapter

# Sync HTTP session (used by check_app_config / send_text helpers, not the async app path).
session = requests.Session()
session.mount('http://', HTTPAdapter(pool_connections=1000, pool_maxsize=1000))
session.mount('https://', HTTPAdapter(pool_connections=1000, pool_maxsize=1000))


def handle_metadata(key=None, value=None):
    """Synchronous metadata get/set (separate sync engine on the metadata bind).

    The async app uses scrapydweb.db.get_metadata/set_metadata; this sync variant
    exists for code that runs outside the event loop (check_app_config, run.py CLI).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from .__version__ import __version__
    from .models import Metadata
    from .vars import SQLALCHEMY_BINDS

    engine = create_engine(SQLALCHEMY_BINDS['metadata'])
    s = sessionmaker(bind=engine)()
    try:
        metadata = s.query(Metadata).filter_by(version=__version__).first()
        if key is None:
            return {k: v for k, v in metadata.__dict__.items() if not k.startswith('_')} if metadata else {}
        if metadata is not None:
            try:
                setattr(metadata, key, value)
                s.commit()
            except Exception:
                print(traceback.format_exc())
                s.rollback()
    finally:
        s.close()
        engine.dispose()


def find_scrapydweb_settings_py(filename, path, prevpath=None):
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, filename)
    if os.path.exists(cfgfile):
        return cfgfile


def get_now_string(allow_space=False):
    if allow_space:
        return time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return time.strftime('%Y-%m-%dT%H_%M_%S')


def handle_slash(string):
    if not string:
        return string
    return string.replace('\\', '/')


def json_dumps(obj, sort_keys=True, indent=4, ensure_ascii=False):
    return json.dumps(obj, sort_keys=sort_keys, indent=indent, ensure_ascii=ensure_ascii)


def get_job_without_ext(job):
    if job.endswith('.tar.gz'):
        return job[:-len('.tar.gz')]
    return os.path.splitext(job)[0]
