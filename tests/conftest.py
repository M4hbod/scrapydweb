# coding: utf-8
import os
from contextlib import nullcontext

import pytest
from starlette.testclient import TestClient

from scrapydweb import create_app
from tests import utils
from tests.fake_scrapyd import FakeScrapyd
from tests.utils import cst, extract_test_data


custom_settings = dict(
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

    ENABLE_SLACK_ALERT=os.environ.get('ENABLE_SLACK_ALERT', 'True') == 'True',
    ENABLE_TELEGRAM_ALERT=os.environ.get('ENABLE_TELEGRAM_ALERT', 'True') == 'True',
    ENABLE_EMAIL_ALERT=os.environ.get('ENABLE_EMAIL_ALERT', 'True') == 'True',
)

extract_test_data()


def make_app(scrapyd_server, scrapyd_auth, extra=None):
    """Build the test app config for one real node + the unreachable fake-domain node."""
    fake_server = 'scrapydweb-fake-domain.com:443'
    SCRAPYD_SERVERS = [scrapyd_server, fake_server]
    if scrapyd_auth:
        authed_server = '%s:%s@%s' % (scrapyd_auth[0], scrapyd_auth[1], scrapyd_server)
        _SCRAPYD_SERVERS = [authed_server, fake_server]
    else:
        _SCRAPYD_SERVERS = SCRAPYD_SERVERS

    config = dict(
        TESTING=True,
        MAIN_PID=os.getpid(),

        SCRAPYD_SERVERS=SCRAPYD_SERVERS,
        _SCRAPYD_SERVERS=_SCRAPYD_SERVERS,
        SCRAPYD_SERVERS_AUTHS=[scrapyd_auth, ('username', '123456abcdef')],
        SCRAPYD_SERVERS_GROUPS=['', 'Scrapyd-group'],
        SCRAPY_PROJECTS_DIR=os.path.join(cst.ROOT_DIR, 'data'),

        STATS_COLLECT_INTERVAL=0,  # the suite invokes the collector explicitly

        ALERT_WORKING_DAYS=list(range(1, 8)),
        ALERT_WORKING_HOURS=list(range(24)),

        VERBOSE=True,
    )
    config.update(custom_settings)
    if extra:
        config.update(extra)

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
    return app


@pytest.fixture(scope='session')
def fake_scrapyd():
    """In-process fake scrapyd (uvicorn daemon thread, random port)."""
    fs = FakeScrapyd().start()
    yield fs
    fs.stop()


@pytest.fixture(scope='session', autouse=True)
def _migrate_once():
    """Run alembic on the first create_app only; later apps skip it (schema is fixed)."""
    import scrapydweb.db as db
    real = db._run_db_migrations
    done = {}

    def once():
        if not done:
            real()
            done['x'] = True

    mp = pytest.MonkeyPatch()
    mp.setattr(db, '_run_db_migrations', once)
    yield
    mp.undo()


@pytest.fixture
def app(fake_scrapyd):
    yield make_app(fake_scrapyd.address, ('admin', '12345'))


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
