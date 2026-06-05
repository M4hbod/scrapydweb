# coding: utf-8
"""Settings page (ports views/system/settings.py)."""
from collections import OrderedDict, defaultdict
import re

from fastapi import APIRouter, Depends, Request
from logparser import SETTINGS_PY_PATH as LOGPARSER_SETTINGS_PY_PATH
from logparser import __version__ as LOGPARSER_VERSION

from ..common import handle_slash, json_dumps as _json_dumps
from ..context import NodeContext, get_node_context
from ..templating import render
from ..vars import (APSCHEDULER_DATABASE_URI, ALERT_TRIGGER_KEYS, DATA_PATH,
                    PYTHON_VERSION, SCHEDULER_STATE_DICT, SCRAPY_VERSION, SCRAPYD_VERSION,
                    SCHEDULE_ADDITIONAL, SQLALCHEMY_BINDS, SQLALCHEMY_DATABASE_URI)
from ..scheduler import scheduler
from ..__version__ import __version__ as SCRAPYDWEB_VERSION

router = APIRouter()


def json_dumps(obj, sort_keys=False):
    s = _json_dumps(obj, sort_keys=sort_keys)
    return s.replace(' true', ' True').replace(' false', ' False').replace(' null', ' None')


def protect(string):
    if not isinstance(string, str):
        return string
    length = len(string)
    if length < 4:
        return '*' * length
    elif length < 12:
        return ''.join([string[i] if not i % 2 else '*' for i in range(0, length)])
    return re.sub(r'^.{4}(.*?).{4}$', r'****\1****', string)


def hide_account(string):
    return re.sub(r'//.+@', '//', string)


@router.get('/{node:int}/settings/', name='settings')
async def settings_page(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    s = request.app.state.settings
    g = s.get
    k = {}

    k['DEFAULT_SETTINGS_PY_PATH'] = handle_slash(g('DEFAULT_SETTINGS_PY_PATH', ''))
    k['SCRAPYDWEB_SETTINGS_PY_PATH'] = handle_slash(g('SCRAPYDWEB_SETTINGS_PY_PATH', ''))
    k['MAIN_PID'] = g('MAIN_PID')
    k['LOGPARSER_PID'] = g('LOGPARSER_PID')
    k['POLL_PID'] = g('POLL_PID')

    k['python_version'] = PYTHON_VERSION
    k['scrapydweb_version'] = SCRAPYDWEB_VERSION
    k['scrapydweb_server'] = json_dumps(dict(
        SCRAPYDWEB_BIND=g('SCRAPYDWEB_BIND', '0.0.0.0'),
        SCRAPYDWEB_PORT=g('SCRAPYDWEB_PORT', 5000),
        URL_SCRAPYDWEB=g('URL_SCRAPYDWEB', 'http://127.0.0.1:5000'),
        ENABLE_AUTH=g('ENABLE_AUTH', False),
        USERNAME=protect(g('USERNAME', '')),
        PASSWORD=protect(g('PASSWORD', ''))))
    k['ENABLE_HTTPS'] = g('ENABLE_HTTPS', False)
    k['enable_https_details'] = json_dumps(dict(
        CERTIFICATE_FILEPATH=g('CERTIFICATE_FILEPATH', ''),
        PRIVATEKEY_FILEPATH=g('PRIVATEKEY_FILEPATH', '')))

    k['scrapy_version'] = SCRAPY_VERSION
    k['SCRAPY_PROJECTS_DIR'] = handle_slash(g('SCRAPY_PROJECTS_DIR', '')) or "''"

    k['scrapyd_version'] = SCRAPYD_VERSION
    servers = defaultdict(list)
    groups = s.get('SCRAPYD_SERVERS_GROUPS', []) or ['']
    auths = s.get('SCRAPYD_SERVERS_AUTHS', []) or [None]
    for group, server, auth in zip(groups, ctx.SCRAPYD_SERVERS, auths):
        _server = '%s:%s@%s' % (protect(auth[0]), protect(auth[1]), server) if auth else server
        servers[group].append(_server)
    k['servers'] = json_dumps(servers)
    k['CHECK_SCRAPYD_SERVERS'] = g('CHECK_SCRAPYD_SERVERS', True)
    k['LOCAL_SCRAPYD_SERVER'] = g('LOCAL_SCRAPYD_SERVER', '') or "''"
    k['LOCAL_SCRAPYD_LOGS_DIR'] = handle_slash(g('LOCAL_SCRAPYD_LOGS_DIR', '')) or "''"
    k['SCRAPYD_LOG_EXTENSIONS'] = g('SCRAPYD_LOG_EXTENSIONS', []) or ['.log', '.log.gz', '.txt', '.gz', '']

    k['ENABLE_LOGPARSER'] = g('ENABLE_LOGPARSER', False)
    k['logparser_version'] = LOGPARSER_VERSION
    k['logparser_settings_py_path'] = handle_slash(LOGPARSER_SETTINGS_PY_PATH)
    k['BACKUP_STATS_JSON_FILE'] = g('BACKUP_STATS_JSON_FILE', True)

    k['scheduler_state'] = SCHEDULER_STATE_DICT[scheduler.state]
    k['JOBS_SNAPSHOT_INTERVAL'] = g('JOBS_SNAPSHOT_INTERVAL', 300)
    k['CHECK_TASK_RESULT_INTERVAL'] = g('CHECK_TASK_RESULT_INTERVAL', 300)
    k['KEEP_TASK_RESULT_LIMIT'] = g('KEEP_TASK_RESULT_LIMIT', 1000)
    k['KEEP_TASK_RESULT_WITHIN_DAYS'] = g('KEEP_TASK_RESULT_WITHIN_DAYS', 31)

    k['run_spider_details'] = json_dumps(dict(
        SCHEDULE_EXPAND_SETTINGS_ARGUMENTS=g('SCHEDULE_EXPAND_SETTINGS_ARGUMENTS', False),
        SCHEDULE_CUSTOM_USER_AGENT=g('SCHEDULE_CUSTOM_USER_AGENT', 'Mozilla/5.0'),
        SCHEDULE_USER_AGENT=g('SCHEDULE_USER_AGENT', None),
        SCHEDULE_ROBOTSTXT_OBEY=g('SCHEDULE_ROBOTSTXT_OBEY', None),
        SCHEDULE_COOKIES_ENABLED=g('SCHEDULE_COOKIES_ENABLED', None),
        SCHEDULE_CONCURRENT_REQUESTS=g('SCHEDULE_CONCURRENT_REQUESTS', None),
        SCHEDULE_DOWNLOAD_DELAY=g('SCHEDULE_DOWNLOAD_DELAY', None),
        SCHEDULE_ADDITIONAL=g('SCHEDULE_ADDITIONAL', SCHEDULE_ADDITIONAL)))

    k['page_display_details'] = json_dumps(dict(
        SHOW_SCRAPYD_ITEMS=g('SHOW_SCRAPYD_ITEMS', True),
        SHOW_JOBS_JOB_COLUMN=g('SHOW_JOBS_JOB_COLUMN', False),
        JOBS_FINISHED_JOBS_LIMIT=g('JOBS_FINISHED_JOBS_LIMIT', 0),
        JOBS_RELOAD_INTERVAL=g('JOBS_RELOAD_INTERVAL', 300),
        DAEMONSTATUS_REFRESH_INTERVAL=g('DAEMONSTATUS_REFRESH_INTERVAL', 10)))

    k['slack_details'] = json_dumps(dict(
        SLACK_TOKEN=protect(g('SLACK_TOKEN', '')), SLACK_CHANNEL=g('SLACK_CHANNEL', '') or 'general'))
    k['telegram_details'] = json_dumps(dict(
        TELEGRAM_TOKEN=protect(g('TELEGRAM_TOKEN', '')), TELEGRAM_CHAT_ID=g('TELEGRAM_CHAT_ID', 0)))
    k['email_details'] = json_dumps(dict(EMAIL_SUBJECT=g('EMAIL_SUBJECT', '') or 'Email from #scrapydweb'))
    email_sender = g('EMAIL_SENDER', '')
    k['email_sender_recipients'] = json_dumps(dict(
        EMAIL_USERNAME=g('EMAIL_USERNAME', '') or email_sender,
        EMAIL_PASSWORD=protect(g('EMAIL_PASSWORD', '')),
        EMAIL_SENDER=email_sender,
        EMAIL_RECIPIENTS=g('EMAIL_RECIPIENTS', [])))
    k['email_smtp_settings'] = json_dumps(dict(
        SMTP_SERVER=g('SMTP_SERVER', ''), SMTP_PORT=g('SMTP_PORT', 0),
        SMTP_OVER_SSL=g('SMTP_OVER_SSL', False), SMTP_CONNECTION_TIMEOUT=g('SMTP_CONNECTION_TIMEOUT', 30)))

    k['ENABLE_MONITOR'] = g('ENABLE_MONITOR', False)
    k['poll_interval'] = json_dumps(dict(
        POLL_ROUND_INTERVAL=g('POLL_ROUND_INTERVAL', 300),
        POLL_REQUEST_INTERVAL=g('POLL_REQUEST_INTERVAL', 10)))
    k['alert_switcher'] = json_dumps(dict(
        ENABLE_SLACK_ALERT=g('ENABLE_SLACK_ALERT', False),
        ENABLE_TELEGRAM_ALERT=g('ENABLE_TELEGRAM_ALERT', False),
        ENABLE_EMAIL_ALERT=g('ENABLE_EMAIL_ALERT', False)))
    k['alert_working_time'] = json_dumps([
        dict(ALERT_WORKING_DAYS="%s" % sorted(g('ALERT_WORKING_DAYS', [])), remark="Monday is 1 and Sunday is 7"),
        dict(ALERT_WORKING_HOURS="%s" % sorted(g('ALERT_WORKING_HOURS', [])), remark="From 0 to 23")])

    d = OrderedDict()
    d['ON_JOB_RUNNING_INTERVAL'] = g('ON_JOB_RUNNING_INTERVAL', 0)
    d['ON_JOB_FINISHED'] = g('ON_JOB_FINISHED', False)
    for key in ALERT_TRIGGER_KEYS:
        keys = ['LOG_%s_THRESHOLD' % key, 'LOG_%s_TRIGGER_STOP' % key, 'LOG_%s_TRIGGER_FORCESTOP' % key]
        d[key] = {kk: g(kk, 0 if kk.endswith('THRESHOLD') else False) for kk in keys}
    value = json_dumps(d)
    value = re.sub(r'True', "<b style='color: red'>True</b>", value)
    value = re.sub(r'(\s[1-9]\d*)', r"<b style='color: red'>\1</b>", value)
    k['alert_triggers'] = value

    k['DEBUG'] = g('DEBUG', False)
    k['VERBOSE'] = g('VERBOSE', False)
    k['DATA_PATH'] = DATA_PATH
    k['database_details'] = json_dumps(dict(
        APSCHEDULER_DATABASE_URI=hide_account(APSCHEDULER_DATABASE_URI),
        SQLALCHEMY_DATABASE_URI=hide_account(SQLALCHEMY_DATABASE_URI),
        SQLALCHEMY_BINDS_METADATA=hide_account(SQLALCHEMY_BINDS['metadata']),
        SQLALCHEMY_BINDS_JOBS=hide_account(SQLALCHEMY_BINDS['jobs'])))

    return render(request, 'scrapydweb/settings.html', node, ctx, page=k)
