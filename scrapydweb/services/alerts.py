# coding: utf-8
"""Collector-driven alert engine.

evaluate_alerts() runs inside the stats collector right after a job's log has
been parsed: compares log-category counts against the LOG_*_THRESHOLD settings,
optionally stops/force-stops the job on scrapyd, fires ON_JOB_FINISHED /
ON_JOB_RUNNING_INTERVAL notifications, and dedupes via JobStats.alert_state.
"""
import json
import logging
import time
from datetime import datetime

from ..common import session
from ..vars import ALERT_TRIGGER_KEYS
from . import notify

logger = logging.getLogger(__name__)


def _within_working_time(settings, now=None):
    """Empty days/hours lists mean alerts are disabled (legacy semantics)."""
    days = settings.get('ALERT_WORKING_DAYS', []) or []
    hours = settings.get('ALERT_WORKING_HOURS', []) or []
    now = now or datetime.now()
    return (now.isoweekday() in days) and (now.hour in hours)


def _cancel_job(server, auth, project, job, times=1):
    for _ in range(times):
        try:
            session.post('http://%s/cancel.json' % server,
                         data=dict(project=project, job=job), auth=auth, timeout=30)
        except Exception as err:
            logger.warning('cancel %s/%s on %s failed: %s', project, job, server, err)


def evaluate_alerts(settings, server, node, auth, row, stats, running):
    """Evaluate triggers for one job after a fresh parse. Mutates row.alert_state."""
    state = {}
    if row.alert_state:
        try:
            state = json.loads(row.alert_state)
        except ValueError:
            state = {}
    dirty = False
    lines = []
    stop_action = None  # 'stop' | 'forcestop'

    categories = stats.get('log_categories') or {}
    for kind in ALERT_TRIGGER_KEYS:
        threshold = settings.get('LOG_%s_THRESHOLD' % kind, 0) or 0
        if threshold <= 0:
            continue
        count = (categories.get('%s_logs' % kind.lower()) or {}).get('count', 0) or 0
        if count < threshold or state.get(kind) == count:
            continue
        state[kind] = count
        dirty = True
        lines.append('%s: %s (threshold %s)' % (kind, count, threshold))
        if settings.get('LOG_%s_TRIGGER_FORCESTOP' % kind, False):
            stop_action = 'forcestop'
        elif settings.get('LOG_%s_TRIGGER_STOP' % kind, False) and stop_action != 'forcestop':
            stop_action = 'stop'

    finished = bool(stats.get('finish_reason') and stats.get('finish_reason') != 'N/A')
    if finished and settings.get('ON_JOB_FINISHED', False) and not state.get('finished'):
        state['finished'] = True
        dirty = True
        lines.append('job finished: %s' % stats.get('finish_reason'))

    interval = settings.get('ON_JOB_RUNNING_INTERVAL', 0) or 0
    if running and interval > 0:
        last = state.get('last_running_alert_ts', 0) or 0
        if time.time() - last >= interval:
            state['last_running_alert_ts'] = time.time()
            dirty = True
            lines.append('job still running (pages: %s, items: %s)'
                         % (stats.get('pages'), stats.get('items')))

    if stop_action and running:
        _cancel_job(server, auth, row.project, row.job,
                    times=2 if stop_action == 'forcestop' else 1)
        lines.append('action: %s sent to scrapyd' % stop_action)

    if dirty:
        row.alert_state = json.dumps(state)

    if lines and _within_working_time(settings):
        url = '%s/log/%s/stats/%s/%s/%s' % (
            settings.get('URL_SCRAPYDWEB', 'http://127.0.0.1:5000'),
            node, row.project, row.spider, row.job)
        subject = '[scrapydweb] %s/%s %s' % (row.project, row.spider, row.job)
        text = subject + '\n' + '\n'.join(lines) + '\n' + url
        notify.dispatch(settings, subject, text)

    return lines
