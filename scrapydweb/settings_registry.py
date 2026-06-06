# coding: utf-8
"""Declarative schema for UI-editable instance settings.

Each field describes one key from default_settings: type, group, how a change
is applied ('live' | 'reschedule' | 'resubprocess' | 'restart') and validation.
Bootstrap keys (DB/paths/bind) are excluded -- env/CLI only.
"""
import os
import re
from dataclasses import dataclass, field

from . import default_settings
from .vars import ALERT_TRIGGER_KEYS, UA_DICT

EMAIL_PATTERN = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
SECRET_SENTINEL = '__secret__'

BOOTSTRAP_KEYS = frozenset({
    'DATA_PATH', 'DATABASE_URL', 'SCRAPYDWEB_BIND', 'SCRAPYDWEB_PORT',
    'ENABLE_HTTPS', 'CERTIFICATE_FILEPATH', 'PRIVATEKEY_FILEPATH', 'SECRET_KEY',
})


@dataclass(frozen=True)
class SettingField:
    key: str
    group: str
    type: str               # bool|int|float|str|list_str|list_int|enum|secret|servers
    label: str
    help: str = ''
    choices: tuple = ()
    nullable: bool = False  # tri-state SCHEDULE_* keys: null = "use spider default"
    apply: str = 'live'     # live | reschedule | restart
    min: int = None
    textarea: bool = False
    validator: object = None  # callable(value, candidate_settings) -> error str | None


def default_for(key):
    return getattr(default_settings, key)


def _v_dir_or_empty(value, _candidate):
    if value and not os.path.isdir(value):
        return 'directory not found: %s' % value
    return None


def _v_log_extensions(value, _candidate):
    for ext in value:
        if not ext.startswith('.'):
            return "each extension must start with '.' (got %r)" % ext
    return None


def _v_email_or_empty(value, _candidate):
    if value and not EMAIL_PATTERN.search(value):
        return 'not a valid email address: %s' % value
    return None


def _v_email_list(value, _candidate):
    for addr in value:
        if not EMAIL_PATTERN.search(addr):
            return 'not a valid email address: %s' % addr
    return None


def _v_days(value, _candidate):
    if any(d not in range(1, 8) for d in value):
        return 'days must be 1-7 (Monday=1)'
    return None


def _v_hours(value, _candidate):
    if any(h not in range(24) for h in value):
        return 'hours must be 0-23'
    return None


def _v_email_alert(value, candidate):
    if candidate.get('ENABLE_EMAIL_ALERT'):
        for k in ('EMAIL_PASSWORD', 'EMAIL_SENDER', 'EMAIL_RECIPIENTS', 'SMTP_SERVER', 'SMTP_PORT'):
            if not candidate.get(k):
                return 'ENABLE_EMAIL_ALERT requires %s' % k
    return None


F = SettingField
_FIELDS = [
    # ---------------------------------------------------------------- servers
    F('SCRAPYD_SERVERS', 'servers', 'servers', 'Scrapyd servers',
      'The scrapyd nodes this instance manages.', apply='reschedule'),
    F('CHECK_SCRAPYD_SERVERS', 'servers', 'bool', 'Check connectivity on save/boot'),
    F('SCRAPY_PROJECTS_DIR', 'servers', 'str', 'Scrapy projects dir',
      'Directory scanned by the Deploy page.', validator=_v_dir_or_empty),
    F('SCRAPYD_LOG_EXTENSIONS', 'servers', 'list_str', 'Log extensions',
      'Tried in order when fetching job logs.', validator=_v_log_extensions),
    # ---------------------------------------------------------------- deploy
    F('DEPLOY_TOKEN', 'deploy', 'secret', 'CI deploy token',
      'CI pipelines push eggs to POST /api/deploy/push with the X-Deploy-Token '
      'header. Empty disables the endpoint.'),
    # ---------------------------------------------------------------- job stats
    F('STATS_COLLECT_INTERVAL', 'logparser', 'int', 'Stats collect interval (s)',
      'ScrapydWeb fetches and parses job logs from every node at this interval. '
      '0 disables the collector.', apply='reschedule', min=0),
    # ---------------------------------------------------------------- scheduler
    F('JOBS_SNAPSHOT_INTERVAL', 'scheduler', 'int', 'Jobs snapshot interval (s)',
      '0 disables the periodic jobs snapshot.', apply='reschedule', min=0),
    F('CHECK_TASK_RESULT_INTERVAL', 'scheduler', 'int', 'Task-result cleanup interval (s)',
      '0 disables periodic task-result cleanup.', apply='reschedule', min=0),
    F('KEEP_TASK_RESULT_LIMIT', 'scheduler', 'int', 'Keep task results (count)', min=0),
    F('KEEP_TASK_RESULT_WITHIN_DAYS', 'scheduler', 'int', 'Keep task results (days)', min=0),
    # ---------------------------------------------------------------- run_spider
    F('SCHEDULE_EXPAND_SETTINGS_ARGUMENTS', 'run_spider', 'bool', 'Expand settings by default'),
    F('SCHEDULE_CUSTOM_USER_AGENT', 'run_spider', 'str', 'Custom User-Agent'),
    F('SCHEDULE_USER_AGENT', 'run_spider', 'enum', 'Default User-Agent', nullable=True,
      choices=tuple(UA_DICT.keys())),
    F('SCHEDULE_ROBOTSTXT_OBEY', 'run_spider', 'bool', 'Default ROBOTSTXT_OBEY', nullable=True),
    F('SCHEDULE_COOKIES_ENABLED', 'run_spider', 'bool', 'Default COOKIES_ENABLED', nullable=True),
    F('SCHEDULE_CONCURRENT_REQUESTS', 'run_spider', 'int', 'Default CONCURRENT_REQUESTS',
      nullable=True, min=1),
    F('SCHEDULE_DOWNLOAD_DELAY', 'run_spider', 'float', 'Default DOWNLOAD_DELAY',
      nullable=True, min=0),
    F('SCHEDULE_ADDITIONAL', 'run_spider', 'str', 'Default additional args', textarea=True),
    # ---------------------------------------------------------------- display
    F('SHOW_SCRAPYD_ITEMS', 'display', 'bool', 'Show scrapyd items'),
    F('SHOW_JOBS_JOB_COLUMN', 'display', 'bool', 'Show job-id column'),
    F('JOBS_FINISHED_JOBS_LIMIT', 'display', 'int', 'Finished jobs limit', '0 = unlimited', min=0),
    F('JOBS_RELOAD_INTERVAL', 'display', 'int', 'Jobs reload interval (s)', min=0),
    F('DAEMONSTATUS_REFRESH_INTERVAL', 'display', 'int', 'Daemonstatus refresh (s)', min=0),
    # ---------------------------------------------------------------- sendtext
    F('SLACK_TOKEN', 'sendtext', 'secret', 'Slack token'),
    F('SLACK_CHANNEL', 'sendtext', 'str', 'Slack channel'),
    F('TELEGRAM_TOKEN', 'sendtext', 'secret', 'Telegram bot token'),
    F('TELEGRAM_CHAT_ID', 'sendtext', 'int', 'Telegram chat id'),
    F('EMAIL_SUBJECT', 'sendtext', 'str', 'Email subject'),
    F('EMAIL_USERNAME', 'sendtext', 'str', 'Email username', 'Defaults to the sender address.'),
    F('EMAIL_PASSWORD', 'sendtext', 'secret', 'Email password'),
    F('EMAIL_SENDER', 'sendtext', 'str', 'Email sender', validator=_v_email_or_empty),
    F('EMAIL_RECIPIENTS', 'sendtext', 'list_str', 'Email recipients', validator=_v_email_list),
    F('SMTP_SERVER', 'sendtext', 'str', 'SMTP server'),
    F('SMTP_PORT', 'sendtext', 'int', 'SMTP port', min=0),
    F('SMTP_OVER_SSL', 'sendtext', 'bool', 'SMTP over SSL'),
    F('SMTP_CONNECTION_TIMEOUT', 'sendtext', 'int', 'SMTP timeout (s)', min=1),
    # ---------------------------------------------------------------- monitor
    F('ENABLE_SLACK_ALERT', 'monitor', 'bool', 'Slack alerts'),
    F('ENABLE_TELEGRAM_ALERT', 'monitor', 'bool', 'Telegram alerts'),
    F('ENABLE_EMAIL_ALERT', 'monitor', 'bool', 'Email alerts', validator=_v_email_alert),
    F('ALERT_WORKING_DAYS', 'monitor', 'list_int', 'Alert working days',
      'Monday=1 .. Sunday=7. Empty = alerts disabled.', validator=_v_days),
    F('ALERT_WORKING_HOURS', 'monitor', 'list_int', 'Alert working hours',
      '0-23. Empty = alerts disabled.', validator=_v_hours),
    F('ON_JOB_RUNNING_INTERVAL', 'monitor', 'int', 'Alert while running every (s)',
      '0 disables', min=0),
    F('ON_JOB_FINISHED', 'monitor', 'bool', 'Alert when a job finishes'),
    F('URL_SCRAPYDWEB', 'monitor', 'str', 'Public URL',
      'Base URL used in alert notification links. '
      'Empty = derived from the bind address (unreachable from other hosts when '
      'binding 0.0.0.0).'),
    # ---------------------------------------------------------------- system
    F('VERBOSE', 'system', 'bool', 'Verbose logging'),
    F('DEBUG', 'system', 'bool', 'Debug mode', apply='restart'),
]
# the 18 LOG_<kind>_<action> alert-trigger keys
for _kind in ALERT_TRIGGER_KEYS:
    _FIELDS.append(F('LOG_%s_THRESHOLD' % _kind, 'monitor', 'int',
                     '%s threshold' % _kind.capitalize(), '0 disables', min=0))
    _FIELDS.append(F('LOG_%s_TRIGGER_STOP' % _kind, 'monitor', 'bool',
                     '%s: stop job' % _kind.capitalize()))
    _FIELDS.append(F('LOG_%s_TRIGGER_FORCESTOP' % _kind, 'monitor', 'bool',
                     '%s: force-stop job' % _kind.capitalize()))

REGISTRY = {f.key: f for f in _FIELDS}

GROUPS = [
    ('servers', 'Scrapyd Servers'),
    ('deploy', 'CI / Deploy'),
    ('logparser', 'Job Stats'),
    ('scheduler', 'Timer Tasks'),
    ('run_spider', 'Run Spider Defaults'),
    ('display', 'Page Display'),
    ('sendtext', 'Slack / Telegram / Email'),
    ('monitor', 'Alerts'),
    ('system', 'System'),
]

# keys allowed in the DB besides registry keys (stored alongside SCRAPYD_SERVERS)
EXTRA_DB_KEYS = frozenset({'SCRAPYD_SERVERS_PUBLIC_URLS'})


def coerce(field, value):
    """Coerce a JSON value to the field type. Returns (value, error|None)."""
    if value is None:
        if field.nullable:
            return None, None
        return None, 'value required'
    try:
        if field.type == 'bool':
            if not isinstance(value, bool):
                return None, 'expected true/false'
            return value, None
        if field.type == 'int':
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                return None, 'expected an integer'
            value = int(value)
        elif field.type == 'float':
            if isinstance(value, bool):
                return None, 'expected a number'
            value = float(value)
        elif field.type in ('str', 'secret'):
            if not isinstance(value, str):
                return None, 'expected a string'
        elif field.type == 'enum':
            if value not in field.choices:
                return None, 'must be one of %s' % (field.choices,)
        elif field.type == 'list_str':
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                return None, 'expected a list of strings'
            value = [x.strip() for x in value if x.strip()]
        elif field.type == 'list_int':
            if not isinstance(value, list):
                return None, 'expected a list of integers'
            value = [int(x) for x in value]
    except (TypeError, ValueError):
        return None, 'invalid value for type %s' % field.type
    if field.min is not None and isinstance(value, (int, float)) and value < field.min:
        return None, 'must be >= %s' % field.min
    return value, None
