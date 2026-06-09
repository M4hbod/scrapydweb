# coding: utf-8
import glob
import io
import json
import locale
import os
import platform
import re
from shutil import rmtree, copy
import sys
import time
import zipfile

from six import string_types

from logparser import __version__ as logparser_version
from scrapydweb.urls import url_for as _url_for
from scrapydweb.vars import setup_logfile


# The app under test, set by the `app` fixture in conftest.py, so url_for() can be
# called the same way as the old Flask url_for (no request context needed).
_app = None


def set_app(app):
    global _app
    _app = app


def url_for(view, **kws):
    return _url_for(_app, view, **kws)


class Constant(object):
    PROJECT = 'ScrapydWeb_demo'
    VERSION = '2018-01-01T01_01_01'
    SPIDER = 'test'
    JOBID = '2018-01-01T01_01_02'

    FAKE_PROJECT = 'FAKE_PROJECT'
    FAKE_VERSION = 'FAKE_VERSION'
    FAKE_SPIDER = 'FAKE_SPIDER'
    FAKE_JOBID = 'FAKE_JOBID'

    NA = 'N/A'
    OK = 'ok'
    ERROR = 'error'
    BIGINT = 9876543210
    DEFAULT_LATEST_VERSION = 'default: the latest version'
    STRICT_NAME_PATTERN = re.compile(r'[^0-9A-Za-z_]')
    DEMO_JOBID = 'ScrapydWeb_demo'
    DEMO_LOG = 'ScrapydWeb_demo.log'
    DEMO_JSON = 'ScrapydWeb_demo.json'
    DEMO_UNFINISHED_LOG = 'ScrapydWeb_demo_unfinished.log'
    DEMO_UNFINISHED_JSON = 'ScrapydWeb_demo_unfinished.json'

    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    LOGPARSER_VERSION = logparser_version

    # ?flash=Add task #1 successfully, next run at 2019-01-01 00:00:01.176468+08:00. Reload this page
    TASK_NEXT_RUN_TIME_PATTERN = re.compile(r"[ ]task #(\d+).+?next run at (.+?)\.[ ]")

    # default UA: werkzeug/0.14.1
    HEADERS_DICT = dict(
        Chrome={'User-Agent': 'Chrome'},
        iPad={'User-Agent': 'iPad'},
        iPhone={'User-Agent': 'iPhone'},
        Android={'User-Agent': 'Android'},
        IE={'User-Agent': 'msie'},
        EDGE={'User-Agent': 'EDGE'},
    )

    SCRAPY_CFG_DICT = dict(
        demo_only_scrapy_cfg='No module named',  # Result from Scrapyd server
        demo_without_scrapy_cfg='scrapy.cfg not found',

        scrapy_cfg_no_settings_default='No section: &#39;settings&#39;',
        scrapy_cfg_no_section_settings='File contains no section headers.',
        scrapy_cfg_no_option_default='No option &#39;default&#39; in section: &#39;settings&#39;',
        scrapy_cfg_no_option_default_equal='contains parsing errors',
        scrapy_cfg_no_option_default_value='returned non-zero exit status',

        scrapy_cfg_no_deploy_project='',
        scrapy_cfg_no_section_deploy='',
        scrapy_cfg_no_option_project='',
        scrapy_cfg_no_option_project_equal='contains parsing errors',
        scrapy_cfg_no_option_project_value='',
    )

    VIEW_TITLE_MAP = {
        'servers': 'Monitor and control',
        'jobs': 'Get the list of jobs',
        'tasks': 'Get the list of timer tasks',

        'deploy': 'Add a version to a project',
        'schedule': 'Schedule a spider run',
        'projects': 'Get the list of projects uploaded',

        'logs': 'Directory listing for /logs/',
        'parse.upload': 'Upload a scrapy logfile to parse',
        'settings': 'default_settings.py'
    }

    (_language_code, _encoding) = locale.getdefaultlocale()
    WINDOWS_NOT_CP936 = platform.system() == 'Windows' and _encoding != 'cp936'


cst = Constant()


def get_text(response):
    return response.text


def req(app, client, view='', kws=None, url='', data=None,
        headers=None, content_type='multipart/form-data',
        ins=None, nos=None, jskws=None, jskeys=None, location=None,
        single_scrapyd=False, set_to_second=False, save=''):
    if single_scrapyd:
        set_single_scrapyd(app, set_to_second)

    if True:
        if not url:
            url = url_for(view, **kws)
        if data is not None:
            form, files = _split_form_files(data)
            response = client.post(url, headers=headers, data=form, files=files or None)
        else:
            response = client.get(url, headers=headers)
        if save:
            with io.open('%s.html' % save, 'wb') as f:
                f.write(response.content)
        text = get_text(response)
        try:
            # js = response.get_json()
            js = json.loads(text)
        except (TypeError, ValueError) as err:  # issubclass(JSONDecodeError, ValueError)
            js = {}
            print(time.ctime(), 'text not js:', text)
        else:
            print(time.ctime(), "js: %s" % json.dumps(js, sort_keys=True, indent=4, ensure_ascii=False))
        try:
            if isinstance(ins, string_types):
                try:
                    print("ins: %s" % ins)
                except:  # For compatibility with Win10 Python2
                    print("ins: %s" % repr(ins))
                assert ins in text, "%s is not found in %s" % (ins, text)
            elif isinstance(ins, list):
                for i in ins:
                    try:
                        print("ins: %s" % i)
                    except:
                        print("ins: %s" % repr(i))
                    assert i in text, "%s is not found in %s" % (i, text)
            elif ins:
                raise TypeError("The argument 'ins' should be either a string or a list")

            if isinstance(nos, string_types):
                print("nos: %s" % nos)
                assert nos not in text, "%s is found in %s" % (nos, text)
            elif isinstance(nos, list):
                for n in nos:
                    print("nos: %s" % n)
                    assert n not in text, "%s is found in %s" % (n, text)
            elif nos:
                raise TypeError("The argument 'nos' should be either a string or a list")

            if location:
                print("response.headers['Location']: %s" % response.headers['Location'])
                print("location: %s" % location)
                try:
                    assert response.headers['Location'].endswith(location)
                except AssertionError:
                    assert location in response.headers['Location']

            if jskws:
                for k, v in jskws.items():
                    print("jskws: %s = %s" % (k, v))
                    try:
                        assert js[k] == v
                    except AssertionError:
                        # v is an element of js[k] or a substring of js[k]
                        assert v in js[k]

            if jskeys:
                if isinstance(jskeys, string_types):
                    print("jskeys: %s" % jskeys)
                    assert jskeys in js.keys()
                elif isinstance(jskeys, list):
                    for k in jskeys:
                        print("jskeys: %s" % k)
                        assert k in js.keys()
                elif jskeys:
                    raise TypeError("The argument 'jskeys' should be either a string or a list")
        except:
            with io.open('response.html', 'wb') as f:
                f.write(response.content)
            raise

        return text, js


def _split_form_files(data):
    """Split a Flask-style test data dict into httpx (form, files).

    File fields are passed as a (path, filename) tuple (the old Werkzeug test
    client format); everything else is a plain form field.
    """
    form, files = {}, {}
    for key, value in data.items():
        if isinstance(value, tuple):
            src, filename = value[0], value[1]
            if hasattr(src, 'read'):          # file-like (e.g. BytesIO)
                fileobj = src
            elif isinstance(src, (bytes, bytearray)):
                fileobj = io.BytesIO(src)
            else:                              # filesystem path
                fileobj = open(src, 'rb')
            files[key] = (filename, fileobj)
        else:
            form[key] = value
    return form, files


def req_single_scrapyd(*args, **kwargs):
    kwargs.update(single_scrapyd=True)
    return req(*args, **kwargs)


def set_single_scrapyd(app, set_to_second=False):
    if len(app.config['SCRAPYD_SERVERS']) > 1:
        index = -1 if set_to_second else 0
        app.config['SCRAPYD_SERVERS'] = [app.config['SCRAPYD_SERVERS'][index]]
        app.config['SCRAPYD_SERVERS_AUTHS'] = [app.config['SCRAPYD_SERVERS_AUTHS'][index]]
        app.config['SCRAPYD_SERVERS_AMOUNT'] = 1


def switch_scrapyd(app):
    if len(app.config['SCRAPYD_SERVERS']) > 1:
        app.config['SCRAPYD_SERVERS'] = app.config['SCRAPYD_SERVERS'][::-1]
        app.config['SCRAPYD_SERVERS_AUTHS'] = app.config['SCRAPYD_SERVERS_AUTHS'][::-1]


def sleep(seconds=4):
    # The no-arg sleep() waits for a spider job to reach a state; the demo spider's
    # DOWNLOAD_DELAY was lowered, so 4s is enough. Override via TEST_SLEEP if needed.
    # Explicit sleep(N) calls (cron-aligned task tests) pass their own N and are left as-is.
    seconds = int(os.environ.get('TEST_SLEEP', seconds)) if seconds == 4 else seconds
    print(time.ctime(), "Sleep %ss" % seconds)
    time.sleep(seconds)


def replace_file_content(filepath, old, new):
    with io.open(filepath, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(content.replace(old, new))
        print("replace %s to %s in %s" % (old, new, filepath))


def extract_test_data():
    """Fast-suite setup: fresh tests/data from data.zip + clean logfile."""
    setup_logfile(delete=True)
    print("setup_logfile(delete=True)")

    data_folder = os.path.join(cst.ROOT_DIR, 'data')
    if os.path.isdir(data_folder):
        rmtree(data_folder, ignore_errors=True)
    with zipfile.ZipFile(os.path.join(cst.ROOT_DIR, 'data.zip'), 'r') as f:
        f.extractall(cst.ROOT_DIR)


def setup_scrapyd_logs():
    """Live-suite setup: seed the REAL scrapyd's logs_dir (~/logs) with demo logs."""
    local_scrapyd_logs_dir = os.environ.get('SCRAPYD_LOGS_DIR',
                                            os.path.join(os.path.expanduser('~'), 'logs'))
    if not os.path.isdir(local_scrapyd_logs_dir):
        sys.exit("scrapyd logs dir not found: %s" % repr(local_scrapyd_logs_dir))
    logs_scrapydweb_demo = os.path.join(local_scrapyd_logs_dir, cst.PROJECT)
    if os.path.isdir(logs_scrapydweb_demo):
        rmtree(logs_scrapydweb_demo, ignore_errors=True)
        print("rmtree %s" % logs_scrapydweb_demo)

    project_path = os.path.join(local_scrapyd_logs_dir, cst.PROJECT)
    spider_path = os.path.join(project_path, cst.SPIDER)
    for path in [project_path, spider_path]:
        if not os.path.isdir(path):
            os.mkdir(path)
    src = os.path.join(cst.ROOT_DIR, 'data', cst.DEMO_LOG)
    for filename in [cst.DEMO_LOG, cst.DEMO_UNFINISHED_LOG]:
        dst = os.path.join(spider_path, filename)
        copy(src, dst)
        print("Copied to %s from %s" % (dst, src))
        # 'finish_reason': 'finished',
        if filename == cst.DEMO_UNFINISHED_LOG:
            replace_file_content(dst, "'finish_reason'", "'finish_reason_removed'")
    # remove leftover logparser artifacts from older runs
    for path in [os.path.join(local_scrapyd_logs_dir, 'stats.json'),
                 os.path.join(spider_path, cst.DEMO_JSON),
                 os.path.join(spider_path, cst.DEMO_UNFINISHED_JSON)]:
        if os.path.exists(path):
            os.remove(path)
            print("Deleted: %s" % path)


def setup_env(custom_settings):
    extract_test_data()


def upload_file_deploy(app, client, filename, project, multinode=False,
                       fail=False, redirect_project=None, alert=None):
    data = {
        'project': project,
        'version': cst.VERSION,
        'file': (os.path.join(cst.ROOT_DIR, u'data/%s' % filename), filename)
    }
    if multinode:
        data.update({'1': 'on', '2': 'on', 'checked_amount': '2'})
    if True:
        url = url_for('deploy.upload', node=1)
        form, files = _split_form_files(data)
        response = client.post(url, data=form, files=files or None)
        text = get_text(response)
        if fail:
            assert response.status_code == 200 and "fail - ScrapydWeb" in text
        else:
            url_redirect = url_for('schedule', node=1, project=redirect_project, version=cst.VERSION)
            if multinode:
                assert response.status_code == 200 and "deploy results - ScrapydWeb" in text and url_redirect in text
            else:
                assert response.status_code == 302 and response.headers['Location'].endswith(url_redirect)

        if alert:
            assert alert in text
