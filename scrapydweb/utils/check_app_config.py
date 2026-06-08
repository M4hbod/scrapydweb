# coding: utf-8
import logging
from multiprocessing.dummy import Pool as ThreadPool
import os
import re

from ..common import handle_metadata, handle_slash, json_dumps, session
from ..models import Base, create_jobs_table
from ..utils.scheduler import scheduler
from ..utils.setup_database import test_database_url_pattern
from ..vars import (ALLOWED_SCRAPYD_LOG_EXTENSIONS, ALERT_TRIGGER_KEYS,
                    SCHEDULER_STATE_DICT, STATE_PAUSED, STATE_RUNNING,
                    SCHEDULE_ADDITIONAL, STRICT_NAME_PATTERN, UA_DICT,
                    jobs_table_map)
from .send_email import send_email


logger = logging.getLogger(__name__)

REPLACE_URL_NODE_PATTERN = re.compile(r'(/api/)\d+/')
EMAIL_PATTERN = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
HASH = '#' * 100
# r'^(?:(?:(.*?)\:)(?:(.*?)@))?(.*?)(?:\:(.*?))?(?:#(.*?))?$'
SCRAPYD_SERVER_PATTERN = re.compile(r"""
                                        ^
                                        (?:
                                            (?:(.*?):)      # username:
                                            (?:(.*?)@)      # password@
                                        )?
                                        (.*?)               # ip
                                        (?::(.*?))?         # :port
                                        (?:\#(.*?))?        # #group
                                        $
                                    """, re.X)


def check_app_config(config):
    def check_assert(key, default, is_instance, allow_zero=True, non_empty=False, containing_type=None):
        if is_instance is int:
            if allow_zero:
                should_be = "a non-negative integer"
            else:
                should_be = "a positive integer"
        else:
            should_be = "an instance of %s%s" % (is_instance, ' and not empty' if non_empty else '')

        value = config.setdefault(key, default)
        kws = dict(
            key=key,
            should_be=should_be,
            containing_type=', containing elements of type %s' % containing_type if containing_type else '',
            value="'%s'" % value if isinstance(value, str) else value
        )
        to_assert = u"{key} should be {should_be}{containing_type}. Current value: {value}".format(**kws)

        assert (isinstance(value, is_instance)
                and (not isinstance(value, bool) if is_instance is int else True)  # isinstance(True, int) => True
                and (value > (-1 if allow_zero else 0) if is_instance is int else True)
                and (value if non_empty else True)
                and (all([isinstance(i, containing_type) for i in value]) if containing_type else True)), to_assert

    logger.debug("Checking app config")

    # ScrapydWeb
    check_assert('SCRAPYDWEB_BIND', '0.0.0.0', str, non_empty=True)
    SCRAPYDWEB_PORT = config.setdefault('SCRAPYDWEB_PORT', 5000)
    try:
        assert not isinstance(SCRAPYDWEB_PORT, bool)
        SCRAPYDWEB_PORT = int(SCRAPYDWEB_PORT)
        assert SCRAPYDWEB_PORT > 0
    except (TypeError, ValueError, AssertionError):
        assert False, "SCRAPYDWEB_PORT should be a positive integer. Current value: %s" % SCRAPYDWEB_PORT

    check_assert('ENABLE_HTTPS', False, bool)
    if config.get('ENABLE_HTTPS', False):
        logger.info("HTTPS mode enabled: ENABLE_HTTPS = %s", config['ENABLE_HTTPS'])
        for k in ['CERTIFICATE_FILEPATH', 'PRIVATEKEY_FILEPATH']:
            check_assert(k, '', str, non_empty=True)
            assert os.path.isfile(config[k]), "%s not found: %s" % (k, config[k])
        logger.info("Running in HTTPS mode: %s, %s", config['CERTIFICATE_FILEPATH'], config['PRIVATEKEY_FILEPATH'])

    # honor a user-configured public URL (settings page / env); derive otherwise
    if not config.get('URL_SCRAPYDWEB'):
        _protocol = 'https' if config.get('ENABLE_HTTPS', False) else 'http'
        _bind = config.get('SCRAPYDWEB_BIND', '0.0.0.0')
        _bind = '127.0.0.1' if _bind == '0.0.0.0' else _bind
        config['URL_SCRAPYDWEB'] = '%s://%s:%s' % (_protocol, _bind, config.get('SCRAPYDWEB_PORT', 5000))
    config['URL_SCRAPYDWEB'] = config['URL_SCRAPYDWEB'].rstrip('/')
    handle_metadata('url_scrapydweb', config['URL_SCRAPYDWEB'])
    logger.info("Setting up URL_SCRAPYDWEB: %s", config['URL_SCRAPYDWEB'])

    # Scrapy
    check_assert('SCRAPY_PROJECTS_DIR', '', str)
    SCRAPY_PROJECTS_DIR = config.get('SCRAPY_PROJECTS_DIR', '')
    if SCRAPY_PROJECTS_DIR:
        assert os.path.isdir(SCRAPY_PROJECTS_DIR), "SCRAPY_PROJECTS_DIR not found: %s" % SCRAPY_PROJECTS_DIR
        logger.info("Setting up SCRAPY_PROJECTS_DIR: %s", handle_slash(SCRAPY_PROJECTS_DIR))

    # Scrapyd
    check_assert('CHECK_SCRAPYD_SERVERS', True, bool)
    check_scrapyd_servers(config)
    ensure_jobs_tables(config)

    check_assert('SCRAPYD_LOG_EXTENSIONS', ALLOWED_SCRAPYD_LOG_EXTENSIONS, list, non_empty=True, containing_type=str)
    SCRAPYD_LOG_EXTENSIONS = config.get('SCRAPYD_LOG_EXTENSIONS', ALLOWED_SCRAPYD_LOG_EXTENSIONS)
    assert all([not i or i.startswith('.') for i in SCRAPYD_LOG_EXTENSIONS]), \
        ("SCRAPYD_LOG_EXTENSIONS should be a list like %s. "
         "Current value: %s" % (ALLOWED_SCRAPYD_LOG_EXTENSIONS, SCRAPYD_LOG_EXTENSIONS))
    logger.info("Locating scrapy logfiles with SCRAPYD_LOG_EXTENSIONS: %s", SCRAPYD_LOG_EXTENSIONS)

    # Run Spider
    check_assert('SCHEDULE_EXPAND_SETTINGS_ARGUMENTS', False, bool)
    check_assert('SCHEDULE_CUSTOM_USER_AGENT', '', str)
    config['SCHEDULE_CUSTOM_USER_AGENT'] = config['SCHEDULE_CUSTOM_USER_AGENT'] or 'Mozilla/5.0'
    UA_DICT.update(custom=config['SCHEDULE_CUSTOM_USER_AGENT'])
    if config.get('SCHEDULE_USER_AGENT', None) is not None:
        check_assert('SCHEDULE_USER_AGENT', '', str)
        user_agent = config['SCHEDULE_USER_AGENT']
        assert user_agent in UA_DICT.keys(), \
            "SCHEDULE_USER_AGENT should be any value of %s. Current value: %s" % (UA_DICT.keys(), user_agent)
    if config.get('SCHEDULE_ROBOTSTXT_OBEY', None) is not None:
        check_assert('SCHEDULE_ROBOTSTXT_OBEY', False, bool)
    if config.get('SCHEDULE_COOKIES_ENABLED', None) is not None:
        check_assert('SCHEDULE_COOKIES_ENABLED', False, bool)
    if config.get('SCHEDULE_CONCURRENT_REQUESTS', None) is not None:
        check_assert('SCHEDULE_CONCURRENT_REQUESTS', 16, int, allow_zero=False)
    if config.get('SCHEDULE_DOWNLOAD_DELAY', None) is not None:
        download_delay = config['SCHEDULE_DOWNLOAD_DELAY']
        if isinstance(download_delay, float):
            assert download_delay >= 0.0, \
                "SCHEDULE_DOWNLOAD_DELAY should a non-negative number. Current value: %s" % download_delay
        else:
            check_assert('SCHEDULE_DOWNLOAD_DELAY', 0, int)
    check_assert('SCHEDULE_ADDITIONAL', SCHEDULE_ADDITIONAL, str)

    # Page Display
    check_assert('SHOW_SCRAPYD_ITEMS', True, bool)
    check_assert('SHOW_JOBS_JOB_COLUMN', False, bool)
    check_assert('JOBS_FINISHED_JOBS_LIMIT', 0, int)
    check_assert('JOBS_RELOAD_INTERVAL', 300, int)
    check_assert('DAEMONSTATUS_REFRESH_INTERVAL', 10, int)

    # Send text
    check_assert('SLACK_TOKEN', '', str)
    check_assert('SLACK_CHANNEL', '', str)
    config['SLACK_CHANNEL'] = config['SLACK_CHANNEL'] or 'general'

    check_assert('TELEGRAM_TOKEN', '', str)
    check_assert('TELEGRAM_CHAT_ID', 0, int)

    check_assert('EMAIL_PASSWORD', '', str)
    if config.get('EMAIL_PASSWORD', ''):
        logger.debug("Found EMAIL_PASSWORD, checking email settings")
        check_assert('EMAIL_SUBJECT', '', str)
        check_assert('EMAIL_USERNAME', '', str)  # '' would default to config['EMAIL_SENDER']
        # check_assert('EMAIL_PASSWORD', '', str, non_empty=True)
        check_assert('EMAIL_SENDER', '', str, non_empty=True)
        EMAIL_SENDER = config['EMAIL_SENDER']
        assert re.search(EMAIL_PATTERN, EMAIL_SENDER), \
            "EMAIL_SENDER should contain '@', like 'username@gmail.com'. Current value: %s" % EMAIL_SENDER
        check_assert('EMAIL_RECIPIENTS', [], list, non_empty=True, containing_type=str)
        EMAIL_RECIPIENTS = config['EMAIL_RECIPIENTS']
        assert all([re.search(EMAIL_PATTERN, i) for i in EMAIL_RECIPIENTS]), \
            ("All elements in EMAIL_RECIPIENTS should contain '@', like 'username@gmail.com'. "
             "Current value: %s") % EMAIL_RECIPIENTS
        if not config.get('EMAIL_USERNAME', ''):
            config['EMAIL_USERNAME'] = config['EMAIL_SENDER']

        check_assert('SMTP_SERVER', '', str, non_empty=True)
        check_assert('SMTP_PORT', 0, int, allow_zero=False)
        check_assert('SMTP_OVER_SSL', False, bool)
        check_assert('SMTP_CONNECTION_TIMEOUT', 30, int, allow_zero=False)

    # Monitor & Alert

        check_assert('ENABLE_SLACK_ALERT', False, bool)
        check_assert('ENABLE_TELEGRAM_ALERT', False, bool)
        check_assert('ENABLE_EMAIL_ALERT', False, bool)

        # For compatibility with Python 3 using range()
        try:
            config['ALERT_WORKING_DAYS'] = list(config.get('ALERT_WORKING_DAYS', []))
        except TypeError:
            pass
        check_assert('ALERT_WORKING_DAYS', [], list, non_empty=True, containing_type=int)
        ALERT_WORKING_DAYS = config['ALERT_WORKING_DAYS']
        assert all([not isinstance(i, bool) and i in range(1, 8) for i in ALERT_WORKING_DAYS]), \
            "Element in ALERT_WORKING_DAYS should be between 1 and 7. Current value: %s" % ALERT_WORKING_DAYS

        try:
            config['ALERT_WORKING_HOURS'] = list(config.get('ALERT_WORKING_HOURS', []))
        except TypeError:
            pass
        check_assert('ALERT_WORKING_HOURS', [], list, non_empty=True, containing_type=int)
        ALERT_WORKING_HOURS = config['ALERT_WORKING_HOURS']
        assert all([not isinstance(i, bool) and i in range(24) for i in ALERT_WORKING_HOURS]), \
            "Element in ALERT_WORKING_HOURS should be between 0 and 23. Current value: %s" % ALERT_WORKING_HOURS

        check_assert('ON_JOB_RUNNING_INTERVAL', 0, int)
        check_assert('ON_JOB_FINISHED', False, bool)

        for k in ALERT_TRIGGER_KEYS:
            check_assert('LOG_%s_THRESHOLD' % k, 0, int)
            check_assert('LOG_%s_TRIGGER_STOP' % k, False, bool)
            check_assert('LOG_%s_TRIGGER_FORCESTOP' % k, False, bool)

        if config.get('ENABLE_SLACK_ALERT', False):
            check_assert('SLACK_TOKEN', '', str, non_empty=True)
            check_slack_telegram(config, service='slack')
        if config.get('ENABLE_TELEGRAM_ALERT', False):
            check_assert('TELEGRAM_TOKEN', '', str, non_empty=True)
            check_assert('TELEGRAM_CHAT_ID', 0, int, allow_zero=False)
            check_slack_telegram(config, service='telegram')
        if config.get('ENABLE_EMAIL_ALERT', False):
            check_assert('EMAIL_PASSWORD', '', str, non_empty=True)
            check_email(config)

    # System
    check_assert('DEBUG', False, bool)
    check_assert('VERBOSE', False, bool)
    # if config.get('VERBOSE', False):
        # logging.getLogger('apscheduler').setLevel(logging.DEBUG)
    # else:
        # logging.getLogger('apscheduler').setLevel(logging.WARNING)
    check_assert('DATA_PATH', '', str)
    check_assert('DATABASE_URL', '', str)
    database_url = config.get('DATABASE_URL', '')
    if database_url:
        assert any(test_database_url_pattern(database_url)), "Invalid format of DATABASE_URL: %s" % database_url

    # Apscheduler
    # In __init__.py create_app(): scheduler.start(paused=True)
    if handle_metadata().get('scheduler_state', STATE_RUNNING) != STATE_PAUSED:
        scheduler.resume()
    logger.info("Scheduler for timer tasks: %s", SCHEDULER_STATE_DICT[scheduler.state])

    check_assert('JOBS_SNAPSHOT_INTERVAL', 300, int)
    check_assert('CHECK_TASK_RESULT_INTERVAL', 300, int)
    check_assert('KEEP_TASK_RESULT_LIMIT', 1000, int)
    check_assert('KEEP_TASK_RESULT_WITHIN_DAYS', 31, int)
    check_assert('STATS_COLLECT_INTERVAL', 10, int)
    register_system_jobs(config)


def create_jobs_snapshot(url_jobs, headers, nodes):
    for node in nodes:
        url_jobs = re.sub(REPLACE_URL_NODE_PATTERN, r'\g<1>%s/' % node, url_jobs, count=1)
        try:
            r = session.post(url_jobs, headers=headers, timeout=60)
            assert r.status_code == 200, "Request got status_code: %s" % r.status_code
        except Exception as err:
            print("Fail to create jobs snapshot: %s\n%s" % (url_jobs, err))
        # else:
        #     print(url_jobs, r.status_code)


def delete_task_result(url, headers):
    url = re.sub(r'(\d+/)+$', '', url)
    try:
        r = session.post(url, headers=headers, timeout=60)
        assert r.status_code == 200, "Request got status_code: %s" % r.status_code
    except Exception as err:
        print("Fail to delete task result: %s\n%s" % (url, err))
    # else:
    #     print('delete_task_result', url, r.status_code, r.json())


def ensure_jobs_tables(config):
    """Define + create the per-server jobs tables (shared with the apply engine)."""
    for node, scrapyd_server in enumerate(config['SCRAPYD_SERVERS'], 1):
        # executed multiple times in tests / on live server-list edits
        jobs_table_map[node] = create_jobs_table(re.sub(STRICT_NAME_PATTERN, '_', scrapyd_server))
    from sqlalchemy import create_engine as _ce
    from ..vars import SQLALCHEMY_DATABASE_URI as _URI
    _eng = _ce(_URI)
    Base.metadata.create_all(_eng, checkfirst=True)
    _eng.dispose()
    logger.debug("Created %s tables for jobs", len(jobs_table_map))


def _remove_system_job(job_id):
    try:
        scheduler.remove_job(job_id, jobstore='memory')
    except Exception:
        pass


def register_system_jobs(config):
    """(Re-)register the jobs_snapshot / delete_task_result interval jobs.

    Shared by boot (check_app_config) and the live settings apply engine.
    An interval of 0 removes a previously registered job.
    """
    from ..auth import INTERNAL_TOKEN_HEADER
    headers = {INTERNAL_TOKEN_HEADER: config.get('_INTERNAL_TOKEN', '')}
    url_scrapydweb = config.get('URL_SCRAPYDWEB') or handle_metadata().get(
        'url_scrapydweb', 'http://127.0.0.1:5000')

    interval = config.get('JOBS_SNAPSHOT_INTERVAL', 300)
    if interval:
        kwargs = dict(
            url_jobs=url_scrapydweb + '/api/1/jobs/',
            headers=headers,
            nodes=list(range(1, len(config['SCRAPYD_SERVERS']) + 1)),
        )
        logger.info(scheduler.add_job(id='jobs_snapshot', replace_existing=True,
                                      func=create_jobs_snapshot, args=None, kwargs=kwargs,
                                      trigger='interval', seconds=interval,
                                      misfire_grace_time=60, coalesce=True, max_instances=1, jobstore='memory'))
    else:
        _remove_system_job('jobs_snapshot')

    interval = config.get('CHECK_TASK_RESULT_INTERVAL', 300)
    if interval and (config.get('KEEP_TASK_RESULT_LIMIT', 1000)
                     or config.get('KEEP_TASK_RESULT_WITHIN_DAYS', 31)):
        kwargs = dict(
            url=url_scrapydweb + handle_metadata().get('url_delete_task_result',
                                                       '/1/tasks/xhr/delete/1/2/'),
            headers=headers,
        )
        logger.info(scheduler.add_job(id='delete_task_result', replace_existing=True,
                                      func=delete_task_result, args=None, kwargs=kwargs,
                                      trigger='interval', seconds=interval,
                                      misfire_grace_time=60, coalesce=True, max_instances=1, jobstore='memory'))
    else:
        _remove_system_job('delete_task_result')

    interval = config.get('STATS_COLLECT_INTERVAL', 10)
    if interval:
        from ..services.logstats import collect_all
        logger.info(scheduler.add_job(id='stats_collector', replace_existing=True,
                                      func=collect_all, args=None, kwargs=dict(config=config),
                                      trigger='interval', seconds=interval,
                                      misfire_grace_time=60, coalesce=True,
                                      max_instances=1, jobstore='memory'))
    else:
        _remove_system_job('stats_collector')


def check_scrapyd_servers(config, check_connectivity=None):
    """Parse/normalize SCRAPYD_SERVERS into the 4 derived lists on config.

    check_connectivity=None defers to config['CHECK_SCRAPYD_SERVERS'].

    Prefers config['_SCRAPYD_SERVERS'] (raw 'user:pass@host:port#group' strings)
    when present: the public SCRAPYD_SERVERS list is auth-stripped after a prior
    derivation, so re-deriving from it would lose credentials.
    """
    SCRAPYD_SERVERS = (config.get('_SCRAPYD_SERVERS')
                       or config.get('SCRAPYD_SERVERS', []) or [])
    SCRAPYD_SERVERS_PUBLIC_URLS = config.get('SCRAPYD_SERVERS_PUBLIC_URLS', None) or [''] * len(SCRAPYD_SERVERS)
    assert len(SCRAPYD_SERVERS_PUBLIC_URLS) == len(SCRAPYD_SERVERS), \
        "SCRAPYD_SERVERS_PUBLIC_URLS should have same length with SCRAPYD_SERVERS:\n%s\nvs.\n%s" % (
        SCRAPYD_SERVERS_PUBLIC_URLS, SCRAPYD_SERVERS)

    servers = []
    for idx, (server, public_url) in enumerate(zip(SCRAPYD_SERVERS, SCRAPYD_SERVERS_PUBLIC_URLS)):
        if isinstance(server, tuple):
            assert len(server) == 5, ("Scrapyd server should be a tuple of 5 elements, "
                                      "current value: %s" % str(server))
            usr, psw, ip, port, group = server
        else:
            usr, psw, ip, port, group = re.search(SCRAPYD_SERVER_PATTERN, server.strip()).groups()
        ip = ip.strip() if ip and ip.strip() else '127.0.0.1'
        port = port.strip() if port and port.strip() else '6800'
        group = group.strip() if group and group.strip() else ''
        auth = (usr, psw) if usr and psw else None
        public_url = public_url.strip(' /')
        servers.append((group, ip, port, auth, public_url))

    def key_func(arg):
        _group, _ip, _port, _auth, _public_url = arg
        parts = _ip.split('.')
        parts = [('0' * (3 - len(part)) + part) for part in parts]
        return [_group, '.'.join(parts), int(_port)]

    servers = sorted(set(servers), key=key_func)
    if check_connectivity is None:
        check_connectivity = config.get('CHECK_SCRAPYD_SERVERS', True)
    if check_connectivity:
        check_scrapyd_connectivity(servers)

    config['SCRAPYD_SERVERS'] = ['%s:%s' % (ip, port) for (group, ip, port, auth, public_url) in servers]
    config['SCRAPYD_SERVERS_GROUPS'] = [group for (group, ip, port, auth, public_url) in servers]
    config['SCRAPYD_SERVERS_AUTHS'] = [auth for (group, ip, port, auth, public_url) in servers]
    config['SCRAPYD_SERVERS_PUBLIC_URLS'] = [public_url for (group, ip, port, auth, public_url) in servers]


def check_scrapyd_connectivity(servers):
    logger.debug("Checking connectivity of SCRAPYD_SERVERS...")

    def check_connectivity(server):
        (_group, _ip, _port, _auth, _public_url) = server
        try:
            url = 'http://%s:%s' % (_ip, _port)
            r = session.get(url, auth=_auth, timeout=10)
            assert r.status_code == 200, "%s with auth %s got status_code %s" % (url, _auth, r.status_code)
        except Exception as err:
            logger.error(err)
            return False
        else:
            logger.debug("%s with auth %s got status_code %s" % (url, _auth, r.status_code))
            return True

    # with ThreadPool(min(len(servers), 100)) as pool:  # Works in python 3.3 and up
        # results = pool.map(check_connectivity, servers)
    pool = ThreadPool(min(len(servers), 100))
    results = pool.map(check_connectivity, servers)
    pool.close()
    pool.join()

    print("\nIndex {group:<20} {server:<21} Connectivity Auth".format(
          group='Group', server='Scrapyd IP:Port'))
    print(HASH)
    for idx, ((group, ip, port, auth, public_url), result) in enumerate(zip(servers, results), 1):
        print("{idx:_<5} {group:_<20} {server:_<22} {result:_<11} {auth}".format(
              idx=idx, group=group or 'None', server='%s:%s' % (ip, port), auth=auth, result=str(result)))
    print(HASH + '\n')

    assert any(results), "None of your SCRAPYD_SERVERS could be connected. "


def check_slack_telegram(config, service):
    logger.debug("Trying to send %s..." % service)
    text = '%s alert enabled #scrapydweb' % service.capitalize()
    alert = "Fail to send text via %s, you may need to set 'ENABLE_%s_ALERT = False'" % (
        service.capitalize(), service.upper())
    if service == 'slack':
        url = 'https://slack.com/api/chat.postMessage'
        data = dict(token=config['SLACK_TOKEN'], channel=config['SLACK_CHANNEL'], text=text)
    else:
        url = 'https://api.telegram.org/bot%s/sendMessage' % config['TELEGRAM_TOKEN']
        data = dict(chat_id=config['TELEGRAM_CHAT_ID'], text=text)
    r = None
    try:
        r = session.post(url, data=data, timeout=30)
        js = r.json()
        assert r.status_code == 200 and js['ok'] is True
    except Exception as err:
        logger.error(err)
        logger.error("url: %s", url)
        logger.error("data: %s", data)
        if r is not None:
            logger.error("status_code: %s", r.status_code)
            logger.error("response: %s", r.text)
        assert False, alert
    else:
        logger.info(text)


def check_email(config):
    kwargs = dict(
        email_username=config['EMAIL_USERNAME'],
        email_password=config['EMAIL_PASSWORD'],
        email_sender=config['EMAIL_SENDER'],
        email_recipients=config['EMAIL_RECIPIENTS'],
        smtp_server=config['SMTP_SERVER'],
        smtp_port=config['SMTP_PORT'],
        smtp_over_ssl=config.get('SMTP_OVER_SSL', False),
        smtp_connection_timeout=config.get('SMTP_CONNECTION_TIMEOUT', 30),
    )
    kwargs['to_retry'] = True
    kwargs['subject'] = 'Email alert enabled #scrapydweb'
    kwargs['content'] = json_dumps(dict(EMAIL_SENDER=config['EMAIL_SENDER'],
                                        EMAIL_RECIPIENTS=config['EMAIL_RECIPIENTS']))

    logger.debug("Trying to send email (smtp_connection_timeout=%s)...", config.get('SMTP_CONNECTION_TIMEOUT', 30))
    result, reason = send_email(**kwargs)
    if not result and os.environ.get('TEST_ON_CIRCLECI', 'False') == 'False':
        logger.debug("kwargs for send_email():\n%s", json_dumps(kwargs, sort_keys=False))
    assert result, "Fail to send email. Modify the email settings above or set 'ENABLE_EMAIL_ALERT = False'"
    logger.info(kwargs['subject'])
