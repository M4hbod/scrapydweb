# coding: utf-8
"""ASGI entrypoint for `uvicorn scrapydweb.asgi:app` (e.g. with --reload).

Settings are layered inside create_app(): defaults < env vars < DB-persisted
(UI edits) < test overrides. There is no settings file.
"""
import os

from scrapydweb import create_app
from scrapydweb.settings import _env_bool

app = create_app()

# Optional bootstrap: validate the config + start the LogParser/poll subprocesses
# (the CLI path does this in run.py; uvicorn workers need it opt-in).
if _env_bool('CHECK_APP_CONFIG'):
    # check_app_config touches the metadata table, but tables are normally created in
    # the app lifespan (which runs AFTER import) -- create them sync, first.
    from scrapydweb.db import _tables_for_bind
    from scrapydweb.db_sync import sync_engines
    from scrapydweb.models import Base
    for _bind in (None, 'metadata', 'jobs'):
        _tables = _tables_for_bind(_bind)
        if _tables:
            Base.metadata.create_all(sync_engines[_bind], tables=_tables, checkfirst=True)

    from scrapydweb.common import handle_metadata
    from scrapydweb.utils.check_app_config import check_app_config
    app.config['MAIN_PID'] = os.getpid()
    handle_metadata('main_pid', app.config['MAIN_PID'])
    check_app_config(app.config)
