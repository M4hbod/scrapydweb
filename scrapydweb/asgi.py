# coding: utf-8
"""ASGI entrypoint for `uvicorn scrapydweb.asgi:app` (e.g. with --reload).

Builds the app from default_settings, overlays ./scrapydweb_settings_v11.py if
present, and allows a quick SCRAPYD_SERVERS override via the SCRAPYD_SERVERS env
var (comma-separated, e.g. "admin:12345@127.0.0.1:6800").
"""
import os

from scrapydweb import create_app
from scrapydweb.common import find_scrapydweb_settings_py
from scrapydweb.vars import SCRAPYDWEB_SETTINGS_PY

app = create_app()

_path = find_scrapydweb_settings_py(SCRAPYDWEB_SETTINGS_PY, os.getcwd())
if _path:
    app.config.from_pyfile(_path)

_servers = os.environ.get('SCRAPYD_SERVERS')
if _servers:
    servers = [s.strip() for s in _servers.split(',') if s.strip()]
    app.config['SCRAPYD_SERVERS'] = servers
    # parse user:pass@host:port -> auth tuple per server
    auths = []
    for s in servers:
        if '@' in s and ':' in s.split('@', 1)[0]:
            cred = s.split('@', 1)[0]
            auths.append(tuple(cred.split(':', 1)))
        else:
            auths.append(None)
    app.config['SCRAPYD_SERVERS_AUTHS'] = auths
    app.config['LOCAL_SCRAPYD_SERVER'] = servers[0].split('@')[-1]
