# coding: utf-8
"""Zero-server state: DB-only endpoints work, node endpoints return a friendly 400."""
from starlette.testclient import TestClient

from tests.conftest import authenticate, make_app


def _zero_server_client():
    app = make_app('placeholder:6800', None)
    app.config['SCRAPYD_SERVERS'] = []
    app.config['SCRAPYD_SERVERS_AUTHS'] = []
    app.config['SCRAPYD_SERVERS_GROUPS'] = []
    return app


def test_zero_servers_dashboard_and_nodes(client_factory=None):
    app = _zero_server_client()
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)
        assert c.get('/api/nodes').json()['nodes'] == []
        r = c.get('/api/dashboard')
        assert r.status_code == 200


def test_zero_servers_node_endpoint_400():
    app = _zero_server_client()
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)
        r = c.get('/1/api/daemonstatus/')
        assert r.status_code == 400
        js = r.json()
        assert js['status'] == 'error'
        assert 'no scrapyd servers configured' in js['message']
