# coding: utf-8
import os
from contextlib import nullcontext

import pytest
from starlette.testclient import TestClient

from scrapydweb import create_app
from tests import utils
from tests.utils import cst, setup_env


# Win10 Python2 Scrapyd error: environment can only contain strings
# https://github.com/scrapy/scrapyd/issues/231


# MUST be updated: _SCRAPYD_SERVER and _SCRAPYD_SERVER_AUTH
custom_settings = dict(
    _SCRAPYD_SERVER='127.0.0.1:6800',
    _SCRAPYD_SERVER_AUTH=('admin', '12345'),  # Or None


    SLACK_TOKEN=os.environ.get('SLACK_TOKEN', ''),
    TELEGRAM_TOKEN=os.environ.get('TELEGRAM_TOKEN', ''),
    TELEGRAM_CHAT_ID=int(os.environ.get('TELEGRAM_CHAT_ID', 0)),

    EMAIL_USERNAME=os.environ.get('EMAIL_USERNAME', 'username@qq.com'),
    EMAIL_PASSWORD=os.environ.get('EMAIL_PASSWORD', ''),  # Whether to test email
    EMAIL_SENDER=os.environ.get('EMAIL_SENDER', 'username@qq.com'),
    EMAIL_RECIPIENTS=[os.environ.get('EMAIL_RECIPIENT', 'username@qq.com')],
    SMTP_SERVER='smtp.qq.com',
    SMTP_PORT=465,
    SMTP_OVER_SSL=True,
    SMTP_CONNECTION_TIMEOUT=60,

    EMAIL_USERNAME_=os.environ.get('EMAIL_USERNAME_', 'username@139.com'),
    EMAIL_PASSWORD_=os.environ.get('EMAIL_PASSWORD_', ''),  # Used in test_check_email_with_ssl_false()
    EMAIL_SENDER_=os.environ.get('EMAIL_SENDER_', 'username@139.com'),
    EMAIL_RECIPIENTS_=[os.environ.get('EMAIL_RECIPIENT_', 'username@139.com')],
    SMTP_SERVER_=os.environ.get('SMTP_SERVER_', 'smtp.139.com'),
    SMTP_PORT_=25,
    SMTP_OVER_SSL_=False,
    SMTP_CONNECTION_TIMEOUT_=60,

    ENABLE_SLACK_ALERT=os.environ.get('ENABLE_SLACK_ALERT', 'True') == 'True',
    ENABLE_TELEGRAM_ALERT=os.environ.get('ENABLE_TELEGRAM_ALERT', 'True') == 'True',
    ENABLE_EMAIL_ALERT=os.environ.get('ENABLE_EMAIL_ALERT', 'True') == 'True',
)


setup_env(custom_settings)


@pytest.fixture
def app():
    fake_server = 'scrapydweb-fake-domain.com:443'
    SCRAPYD_SERVERS = [custom_settings['_SCRAPYD_SERVER'], fake_server]
    if custom_settings['_SCRAPYD_SERVER_AUTH']:
        username, password = custom_settings['_SCRAPYD_SERVER_AUTH']
        authed_server = '%s:%s@%s' % (username, password, custom_settings['_SCRAPYD_SERVER'])
        _SCRAPYD_SERVERS = [authed_server, fake_server]
    else:
        _SCRAPYD_SERVERS = SCRAPYD_SERVERS

    config = dict(
        TESTING=True,
        # SERVER_NAME='127.0.0.1:5000',  # http://flask.pocoo.org/docs/0.12/config/#builtin-configuration-values

        MAIN_PID=os.getpid(),

        SCRAPYD_SERVERS=SCRAPYD_SERVERS,
        _SCRAPYD_SERVERS=_SCRAPYD_SERVERS,
        SCRAPYD_SERVERS_AUTHS=[custom_settings['_SCRAPYD_SERVER_AUTH'], ('username', '123456abcdef')],
        SCRAPYD_SERVERS_GROUPS=['', 'Scrapyd-group'],
        SCRAPY_PROJECTS_DIR=os.path.join(cst.ROOT_DIR, 'data'),

        STATS_COLLECT_INTERVAL=0,  # the suite invokes the collector explicitly

        ALERT_WORKING_DAYS=list(range(1, 8)),
        ALERT_WORKING_HOURS=list(range(24)),

        VERBOSE=True,
    )

    config.update(custom_settings)

    app = create_app(config)

    def inject_variable(request=None):
        SCRAPYD_SERVERS = app.config.get('SCRAPYD_SERVERS', []) or ['127.0.0.1:6800']
        return dict(
            SCRAPYD_SERVERS=SCRAPYD_SERVERS,
            SCRAPYD_SERVERS_AMOUNT=len(SCRAPYD_SERVERS),
            SCRAPYD_SERVERS_GROUPS=app.config.get('SCRAPYD_SERVERS_GROUPS', []) or [''],
            SCRAPYD_SERVERS_AUTHS=app.config.get('SCRAPYD_SERVERS_AUTHS', []) or [None],
            SCRAPYD_SERVERS_PUBLIC_URLS=[''] * len(SCRAPYD_SERVERS),

            DAEMONSTATUS_REFRESH_INTERVAL=app.config.get('DAEMONSTATUS_REFRESH_INTERVAL', 10),
            SHOW_SCRAPYD_ITEMS=app.config.get('SHOW_SCRAPYD_ITEMS', True),
        )
    app.state.context_processors.append(inject_variable)

    # Let helpers call url_for(view, **kws) without a request context (see tests/utils.py),
    # and keep `with app.test_request_context():` working as a no-op in legacy test bodies.
    utils.set_app(app)
    app.test_request_context = lambda *a, **k: nullcontext()

    yield app


ADMIN_USER, ADMIN_PASS = 'admin', 'admin-test-pass'


def authenticate(test_client):
    """Create the admin on first use, then log in (session cookie persists)."""
    me = test_client.get('/api/auth/me').json()
    if me.get('setup_required'):
        r = test_client.post('/api/auth/setup', json={'username': ADMIN_USER, 'password': ADMIN_PASS})
        assert r.status_code == 200, r.text
    elif not me.get('authenticated'):
        r = test_client.post('/api/auth/login', json={'username': ADMIN_USER, 'password': ADMIN_PASS})
        assert r.status_code == 200, r.text


@pytest.fixture
def client(app):
    # Starlette's sync TestClient drives the async ASGI app and runs lifespan
    # (DB init) on context entry. follow_redirects=False matches Flask's test client.
    with TestClient(app, follow_redirects=False) as test_client:
        authenticate(test_client)
        yield test_client
