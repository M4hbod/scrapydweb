# coding: utf-8
"""Instance settings API (Windmill-style): DB-backed, edited in the SPA.

GET  /api/settings/schema  -- groups + fields + effective values (+ system info)
PUT  /api/settings         -- {settings: {...}, reset: [...]} -> validate,
                              persist to the `setting` table, apply live.
"""
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from logparser import SETTINGS_PY_PATH as LOGPARSER_SETTINGS_PY_PATH  # noqa: F401 (version import below)
from logparser import __version__ as LOGPARSER_VERSION
from starlette.concurrency import run_in_threadpool

from ..__version__ import __version__ as SCRAPYDWEB_VERSION
from ..scheduler import scheduler
from ..settings_registry import (BOOTSTRAP_KEYS, GROUPS, REGISTRY,
                                 SECRET_SENTINEL, default_for)
from ..settings_store import delete_db_settings, get_db_settings, set_db_settings
from ..vars import (DATA_PATH, PYTHON_VERSION,
                    SCHEDULER_STATE_DICT, SCRAPY_VERSION, SCRAPYD_VERSION,
                    SQLALCHEMY_DATABASE_URI)

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/settings')


def hide_account(string):
    return re.sub(r'//.+@', '//', string)


def _server_rows(s):
    """Zip the derived lists into structured rows for the UI servers editor."""
    servers = s.get('SCRAPYD_SERVERS', []) or []
    groups = s.get('SCRAPYD_SERVERS_GROUPS', []) or [''] * len(servers)
    auths = s.get('SCRAPYD_SERVERS_AUTHS', []) or [None] * len(servers)
    publics = s.get('SCRAPYD_SERVERS_PUBLIC_URLS', None) or [''] * len(servers)
    rows = []
    for idx, server in enumerate(servers):
        host, _, port = server.partition(':')
        auth = auths[idx] if idx < len(auths) else None
        rows.append(dict(
            host=host, port=int(port or 6800),
            username=(auth[0] if auth else ''),
            password=(SECRET_SENTINEL if auth and auth[1] else ''),
            group=groups[idx] if idx < len(groups) else '',
            public_url=publics[idx] if idx < len(publics) else '',
        ))
    return rows


def _field_dto(field, s, sources):
    value = s.get(field.key, default_for(field.key))
    if field.type == 'secret':
        value = SECRET_SENTINEL if value else ''
    default = default_for(field.key)
    if field.type == 'secret':
        default = ''
    return dict(
        key=field.key, type=field.type, label=field.label, help=field.help,
        default=default, value=value, source=sources.get(field.key, 'default'),
        apply=field.apply, secret=field.type == 'secret', nullable=field.nullable,
        choices=list(field.choices) or None, min=field.min, textarea=field.textarea,
    )


@router.get('/schema', name='settings.schema')
async def settings_schema(request: Request):
    app = request.app
    s = app.state.settings
    sources = getattr(app.state, 'settings_sources', {})

    groups = []
    for gid, label in GROUPS:
        fields = [_field_dto(f, s, sources) for f in REGISTRY.values() if f.group == gid]
        groups.append(dict(id=gid, label=label, fields=fields))

    meta = {}
    try:
        from ..db import get_metadata
        meta = await get_metadata()
    except Exception:
        pass

    system_info = dict(
        scrapydweb_version=SCRAPYDWEB_VERSION,
        python_version=PYTHON_VERSION,
        scrapy_version=SCRAPY_VERSION,
        scrapyd_version=SCRAPYD_VERSION,
        logparser_version=LOGPARSER_VERSION,
        DATA_PATH=DATA_PATH,
        MAIN_PID=s.get('MAIN_PID'),
        scheduler_state=SCHEDULER_STATE_DICT[scheduler.state],
        URL_SCRAPYDWEB=s.get('URL_SCRAPYDWEB', meta.get('url_scrapydweb', '')),
        databases=dict(
            default=hide_account(SQLALCHEMY_DATABASE_URI),
        ),
    )

    return JSONResponse(dict(
        status='ok', groups=groups,
        servers_value=_server_rows(s),
        pending_restart=sorted(getattr(app.state, 'pending_restart', set())),
        system_info=system_info,
    ))


def _serialize_server_rows(rows, current):
    """Structured rows -> ('user:pass@host:port#group' strings, public_urls).

    A password of SECRET_SENTINEL keeps the currently-stored password of the
    matching host:port.
    """
    cur_auths = {}
    servers = current.get('SCRAPYD_SERVERS', []) or []
    auths = current.get('SCRAPYD_SERVERS_AUTHS', []) or []
    for idx, server in enumerate(servers):
        cur_auths[server] = auths[idx] if idx < len(auths) else None

    strings, publics = [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('each server must be an object')
        host = str(row.get('host', '')).strip()
        if not host:
            raise ValueError('server host is required')
        port = str(row.get('port') or 6800).strip()
        username = str(row.get('username') or '').strip()
        password = str(row.get('password') or '').strip()
        if password == SECRET_SENTINEL:
            kept = cur_auths.get('%s:%s' % (host, port))
            password = kept[1] if kept else ''
        group = str(row.get('group') or '').strip()
        s = host + ':' + port
        if username and password:
            s = '%s:%s@%s' % (username, password, s)
        if group:
            s += '#' + group
        strings.append(s)
        publics.append(str(row.get('public_url') or '').strip(' /'))
    if not strings:
        raise ValueError('at least one scrapyd server is required')
    return strings, publics


async def save_settings(request: Request):
    from ..utils.apply_settings import apply_changes, validate_changes

    app = request.app
    s = app.state.settings
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({'status': 'error', 'errors': {'_body': 'invalid JSON body'}},
                            status_code=400)
    changes = dict(body.get('settings') or {})
    reset = list(body.get('reset') or [])

    errors = {}
    nodes_changed = False

    # bootstrap / unknown keys
    for key in list(changes) + reset:
        if key in BOOTSTRAP_KEYS:
            errors[key] = 'bootstrap setting -- set via environment variable / CLI'
        elif key not in REGISTRY:
            errors[key] = 'unknown setting'
    if errors:
        return JSONResponse({'status': 'error', 'errors': errors}, status_code=400)

    # secrets: keep-sentinel or empty string = no change
    for key in list(changes):
        field = REGISTRY[key]
        if field.type == 'secret' and changes[key] in ('', SECRET_SENTINEL, None):
            changes.pop(key)

    # structured servers -> internal string format
    public_urls = None
    if 'SCRAPYD_SERVERS' in changes:
        try:
            strings, public_urls = _serialize_server_rows(changes['SCRAPYD_SERVERS'], s)
        except ValueError as err:
            return JSONResponse({'status': 'error',
                                 'errors': {'SCRAPYD_SERVERS': str(err)}}, status_code=400)
        changes['SCRAPYD_SERVERS'] = strings
        nodes_changed = True

    errors = validate_changes(changes, s)
    if errors:
        return JSONResponse({'status': 'error', 'errors': errors}, status_code=400)

    if not changes and not reset:
        return JSONResponse({'status': 'ok', 'results': {}, 'restart_required': False,
                             'nodes_changed': False})

    # persist (servers store the full auth strings + parallel public urls)
    to_store = dict(changes)
    if public_urls is not None:
        to_store['SCRAPYD_SERVERS_PUBLIC_URLS'] = public_urls
    prior = await get_db_settings()  # snapshot for rollback
    await set_db_settings(to_store)

    apply_input = dict(changes)
    if public_urls is not None:
        apply_input['SCRAPYD_SERVERS_PUBLIC_URLS'] = public_urls
    try:
        results = await run_in_threadpool(apply_changes, app, apply_input)
    except ValueError as err:
        # roll back the rows we just wrote to their prior state
        restore = {k: prior[k] for k in to_store if k in prior}
        if restore:
            await set_db_settings(restore)
        await delete_db_settings([k for k in to_store if k not in prior])
        return JSONResponse({'status': 'error',
                             'errors': {'SCRAPYD_SERVERS': str(err)}}, status_code=400)

    # resets: delete rows + restore defaults live
    if reset:
        to_delete = list(reset)
        if 'SCRAPYD_SERVERS' in reset:
            to_delete.append('SCRAPYD_SERVERS_PUBLIC_URLS')  # stored alongside
        await delete_db_settings(to_delete)
        for key in reset:
            s[key] = default_for(key)
            app.state.settings_sources[key] = 'default'
            results[key] = 'applied'

    restart_required = any(v == 'restart_required' for v in results.values())
    return JSONResponse({'status': 'ok', 'results': results,
                         'restart_required': restart_required,
                         'nodes_changed': nodes_changed})


router.add_api_route('', save_settings, methods=['PUT', 'POST'], name='settings.save')
router.add_api_route('/', save_settings, methods=['PUT', 'POST'], name='settings.save_slash')
