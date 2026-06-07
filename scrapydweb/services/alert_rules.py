# coding: utf-8
"""Per-project/spider alert rules.

A rule's non-null fields overlay the global alert settings for jobs whose
project/spider match its fnmatch patterns. Matching rules apply least-specific
first, so the most specific value wins per field. evaluate_alerts() itself is
untouched: it just receives the effective settings dict.

load_rules_sync() runs in the collector thread (no event loop) -- sync session.
"""
import fnmatch
import json
import logging

from sqlalchemy import select

from ..models import AlertRule
from ..vars import ALERT_TRIGGER_KEYS

logger = logging.getLogger(__name__)

CHANNEL_NAMES = ('slack', 'telegram', 'email')
ACTIONS = (None, 'alert', 'stop', 'forcestop')


def rule_dict(rule):
    try:
        thresholds = json.loads(rule.thresholds_json) if rule.thresholds_json else {}
    except ValueError:
        thresholds = {}
    try:
        channels = json.loads(rule.channels_json) if rule.channels_json else None
    except ValueError:
        channels = None
    return dict(
        id=rule.id, name=rule.name, enabled=bool(rule.enabled),
        project_pattern=rule.project_pattern, spider_pattern=rule.spider_pattern,
        thresholds=thresholds, on_finished=rule.on_finished,
        on_running_interval=rule.on_running_interval, channels=channels,
        created_at=str(rule.created_at)[:19] if rule.created_at else None,
        updated_at=str(rule.updated_at)[:19] if rule.updated_at else None,
    )


def load_rules_sync():
    """Enabled rules as plain dicts (collector thread; never raises)."""
    from ..db_sync import SyncSessionLocal
    try:
        with SyncSessionLocal() as s:
            rows = s.execute(select(AlertRule).filter_by(enabled=True)
                             .order_by(AlertRule.id)).scalars().all()
            return [rule_dict(r) for r in rows]
    except Exception as err:
        logger.warning('Fail to load alert rules: %s', err)
        return []


def _specificity(rule):
    """Sort key: exact match beats glob beats '*'; project outweighs spider."""
    def score(pattern):
        if pattern == '*':
            return 0
        if any(c in pattern for c in '*?['):
            return 1
        return 2
    return (score(rule['project_pattern']), score(rule['spider_pattern']), rule['id'])


def matching_rules(rules, project, spider):
    """Enabled rules matching (project, spider), least-specific first."""
    matched = [r for r in rules
               if fnmatch.fnmatchcase(project, r['project_pattern'])
               and fnmatch.fnmatchcase(spider, r['spider_pattern'])]
    return sorted(matched, key=_specificity)


def effective_settings(settings, rules, project, spider):
    """Overlay matching rules' non-null fields onto the global alert settings.

    Pure: returns a shallow copy of ``settings`` (same object when no rule
    matches, so the common path stays allocation-free).
    """
    matched = matching_rules(rules, project, spider)
    if not matched:
        return settings
    eff = dict(settings)
    for rule in matched:
        for kind in ALERT_TRIGGER_KEYS:
            spec = (rule['thresholds'] or {}).get(kind)
            if not spec:
                continue
            threshold = spec.get('threshold')
            if threshold is None:
                continue
            action = spec.get('action')
            eff['LOG_%s_THRESHOLD' % kind] = int(threshold)
            eff['LOG_%s_TRIGGER_STOP' % kind] = action == 'stop'
            eff['LOG_%s_TRIGGER_FORCESTOP' % kind] = action == 'forcestop'
        if rule['on_finished'] is not None:
            eff['ON_JOB_FINISHED'] = bool(rule['on_finished'])
        if rule['on_running_interval'] is not None:
            eff['ON_JOB_RUNNING_INTERVAL'] = int(rule['on_running_interval'])
        if rule['channels'] is not None:
            for name in CHANNEL_NAMES:
                eff['ENABLE_%s_ALERT' % name.upper()] = name in rule['channels']
    return eff


def validate_rule_payload(body, partial=False):
    """Validate a CRUD payload. Returns (fields, error)."""
    fields = {}
    if 'name' in body or not partial:
        name = str(body.get('name') or '').strip()
        if not name:
            return None, 'name is required'
        fields['name'] = name
    for key, default in (('project_pattern', '*'), ('spider_pattern', '*')):
        if key in body or not partial:
            pattern = str(body.get(key) or '').strip() or default
            try:
                fnmatch.translate(pattern)
            except Exception:
                return None, 'invalid pattern %r' % pattern
            fields[key] = pattern
    if 'thresholds' in body:
        thresholds = body.get('thresholds') or {}
        if not isinstance(thresholds, dict):
            return None, 'thresholds must be an object'
        cleaned = {}
        for kind, spec in thresholds.items():
            if kind not in ALERT_TRIGGER_KEYS:
                return None, 'unknown log kind %r (one of %s)' % (kind, list(ALERT_TRIGGER_KEYS))
            if not isinstance(spec, dict):
                return None, 'thresholds.%s must be an object' % kind
            threshold = spec.get('threshold')
            if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0:
                return None, 'thresholds.%s.threshold must be an integer >= 0' % kind
            action = spec.get('action')
            if action not in ACTIONS:
                return None, 'thresholds.%s.action must be one of %s' % (kind, list(ACTIONS))
            if threshold > 0:
                cleaned[kind] = dict(threshold=threshold, action=action)
        fields['thresholds_json'] = json.dumps(cleaned) if cleaned else None
    if 'on_finished' in body:
        v = body.get('on_finished')
        if v is not None and not isinstance(v, bool):
            return None, 'on_finished must be true/false/null'
        fields['on_finished'] = v
    if 'on_running_interval' in body:
        v = body.get('on_running_interval')
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
            return None, 'on_running_interval must be an integer >= 0 or null'
        fields['on_running_interval'] = v
    if 'channels' in body:
        v = body.get('channels')
        if v is not None:
            if not isinstance(v, list) or any(c not in CHANNEL_NAMES for c in v):
                return None, 'channels must be null or a list from %s' % (CHANNEL_NAMES,)
            v = json.dumps(sorted(set(v)))
        fields['channels_json'] = v
    if 'enabled' in body:
        fields['enabled'] = bool(body.get('enabled'))
    return fields, None
