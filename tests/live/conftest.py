# coding: utf-8
"""Live-integration fixtures: real scrapyd at 127.0.0.1:6800 (just infra / just scrapyd).

Everything under tests/live/ is auto-marked `live` and excluded from `just test`.
"""
import pytest
from starlette.testclient import TestClient

from tests.conftest import authenticate, make_app
from tests.utils import setup_scrapyd_logs

LIVE_SCRAPYD = '127.0.0.1:6800'
LIVE_AUTH = ('admin', '12345')

_logs_seeded = {}


def pytest_collection_modifyitems(items):
    for item in items:
        if '/tests/live/' in str(item.fspath):
            item.add_marker(pytest.mark.live)


@pytest.fixture
def app():
    if not _logs_seeded:
        setup_scrapyd_logs()  # seed ~/logs (the real scrapyd's logs_dir)
        _logs_seeded['x'] = True
    yield make_app(LIVE_SCRAPYD, LIVE_AUTH)


@pytest.fixture
def client(app):
    with TestClient(app, follow_redirects=False) as test_client:
        authenticate(test_client)
        yield test_client
