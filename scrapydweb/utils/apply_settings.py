# coding: utf-8
"""Validate + live-apply instance-setting changes (the settings PUT endpoint).

Sync code (BackgroundScheduler, handle_metadata, Popen) -- the async route runs
apply_changes via run_in_threadpool. Never calls check_app_config (it fires
live alert test-messages); only check_scrapyd_servers is reused.
"""
import logging

from ..settings_registry import REGISTRY, coerce
from ..vars import UA_DICT

logger = logging.getLogger(__name__)

SERVER_KEYS = {'SCRAPYD_SERVERS', 'SCRAPYD_SERVERS_PUBLIC_URLS', 'CHECK_SCRAPYD_SERVERS'}
RESCHEDULE_KEYS = {'JOBS_SNAPSHOT_INTERVAL', 'CHECK_TASK_RESULT_INTERVAL', 'STATS_COLLECT_INTERVAL',
                   'KEEP_TASK_RESULT_LIMIT', 'KEEP_TASK_RESULT_WITHIN_DAYS'}


def validate_changes(changes, current):
    """Coerce values in place; return {key: error} (empty = valid)."""
    errors = {}
    candidate = dict(current)
    candidate.update(changes)
    for key, value in list(changes.items()):
        field = REGISTRY.get(key)
        if field is None:
            errors[key] = 'unknown or non-editable setting'
            continue
        if field.type == 'servers':
            continue  # already serialized strings; check_scrapyd_servers validates
        coerced, err = coerce(field, value)
        if err:
            errors[key] = err
            continue
        changes[key] = coerced
        candidate[key] = coerced
    if errors:
        return errors
    # field + cross-field validators against the merged candidate
    for key in changes:
        field = REGISTRY.get(key)
        if field is not None and field.validator is not None:
            err = field.validator(candidate.get(key), candidate)
            if err:
                errors[key] = err
    return errors


def apply_changes(app, changes):
    """Apply validated changes to the live app. Returns {key: status}.

    Raises ValueError when SCRAPYD_SERVERS derivation/connectivity fails
    (caller rolls back the DB rows).
    """
    from .check_app_config import (check_scrapyd_servers, ensure_jobs_tables,
                                   register_system_jobs)

    settings = app.state.settings
    results = {}

    # ---- derive server lists on a candidate first (this is the only failure path)
    if SERVER_KEYS & set(changes):
        candidate = dict(settings)
        candidate.update(changes)
        if 'SCRAPYD_SERVERS' in changes:
            # raw authed strings win over any stale _SCRAPYD_SERVERS from boot
            candidate['_SCRAPYD_SERVERS'] = list(changes['SCRAPYD_SERVERS'])
        try:
            check_scrapyd_servers(candidate)
        except AssertionError as err:
            raise ValueError(str(err))
        except Exception as err:
            raise ValueError('Invalid SCRAPYD_SERVERS: %s' % err)
        for key in ('SCRAPYD_SERVERS', 'SCRAPYD_SERVERS_GROUPS',
                    'SCRAPYD_SERVERS_AUTHS', 'SCRAPYD_SERVERS_PUBLIC_URLS'):
            settings[key] = candidate[key]
        if 'SCRAPYD_SERVERS' in changes:
            settings['_SCRAPYD_SERVERS'] = list(changes['SCRAPYD_SERVERS'])

    # ---- live mutation (request path reads this dict per request)
    for key, value in changes.items():
        if key == 'SCRAPYD_SERVERS':
            continue  # derived form already applied above
        settings[key] = value
        app.state.settings_sources[key] = 'db'
        results[key] = 'applied'
    if 'SCRAPYD_SERVERS' in changes:
        app.state.settings_sources['SCRAPYD_SERVERS'] = 'db'
        results['SCRAPYD_SERVERS'] = 'applied'

    if 'SCHEDULE_CUSTOM_USER_AGENT' in changes:
        UA_DICT['custom'] = changes['SCHEDULE_CUSTOM_USER_AGENT']

    if SERVER_KEYS & set(changes):
        try:
            ensure_jobs_tables(settings)
        except Exception as err:
            logger.warning('ensure_jobs_tables failed: %s', err)

    if RESCHEDULE_KEYS & set(changes):
        try:
            register_system_jobs(settings)
        except Exception as err:
            logger.warning('register_system_jobs failed: %s', err)

    # ---- restart-only keys
    for key in changes:
        field = REGISTRY.get(key)
        if field is not None and field.apply == 'restart':
            results[key] = 'restart_required'
            app.state.pending_restart.add(key)

    return results
