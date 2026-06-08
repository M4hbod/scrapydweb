# coding: utf-8
"""Basic JSON API + SPA serving tests (no scrapyd interaction beyond daemonstatus)."""
import os

from tests.utils import cst


def test_app_boots(app):
    assert app.config['TESTING'] is True
    assert len(app.config['SCRAPYD_SERVERS']) == 2


def test_spa_index_served(client):
    dist = os.path.join(os.path.dirname(cst.ROOT_DIR), 'frontend', 'dist', 'index.html')
    if not os.path.isfile(dist):
        import pytest
        pytest.skip('frontend/dist not built')
    for path in ['/', '/jobs', '/tasks', '/settings', '/log/1/utf8/p/s/j']:
        r = client.get(path)
        assert r.status_code == 200, path
        assert '<div id="root">' in r.text, path


def test_nodes(app, client):
    js = client.get('/api/nodes').json()
    nodes = js['nodes']
    assert len(nodes) == 2
    assert nodes[0]['node'] == 1
    assert cst.PROJECT not in nodes[0]['server']  # server string, not project
    assert nodes[0]['server'] == app.config['SCRAPYD_SERVERS'][0]


def test_dashboard(client):
    js = client.get('/api/dashboard').json()
    d = js['dashboard']
    assert d is not None
    assert d['nodes_total'] == 2
    assert set(d['kpi']) == {'running', 'pending', 'finished', 'pages', 'items'}
    assert isinstance(d['nodes'], list) and len(d['nodes']) == 2
    assert isinstance(d['activity'], list)
    assert isinstance(d['throughput'], list)


def test_metadata_password_stripped(client):
    js = client.get('/api/metadata').json()
    assert 'metadata' in js
    assert 'password' not in js['metadata']


def _field(js, key):
    return next(f for g in js['groups'] for f in g['fields'] if f['key'] == key)


def test_settings_schema(client):
    r = client.get('/api/settings/schema')
    assert r.status_code == 200
    js = r.json()
    assert js['status'] == cst.OK
    assert [g['id'] for g in js['groups']]
    f = _field(js, 'DAEMONSTATUS_REFRESH_INTERVAL')
    assert f['type'] == 'int' and f['value'] == 10 and f['source'] == 'default'
    assert js['system_info']['scrapydweb_version']
    # the scrapyd auth password never appears; secrets are masked
    assert '12345' not in r.text
    for g in js['groups']:
        for fld in g['fields']:
            if fld['secret']:
                assert fld['value'] in ('', '__secret__')


def test_settings_put_roundtrip(app, client):
    r = client.put('/api/settings', json={'settings': {'DAEMONSTATUS_REFRESH_INTERVAL': 42}})
    assert r.status_code == 200
    js = r.json()
    assert js['results']['DAEMONSTATUS_REFRESH_INTERVAL'] == 'applied'
    assert app.config['DAEMONSTATUS_REFRESH_INTERVAL'] == 42
    f = _field(client.get('/api/settings/schema').json(), 'DAEMONSTATUS_REFRESH_INTERVAL')
    assert f['value'] == 42 and f['source'] == 'db'


def test_settings_put_invalid(app, client):
    before = app.config['DAEMONSTATUS_REFRESH_INTERVAL']
    for bad in (-5, 'abc'):
        r = client.put('/api/settings', json={'settings': {'DAEMONSTATUS_REFRESH_INTERVAL': bad}})
        assert r.status_code == 400
        assert 'DAEMONSTATUS_REFRESH_INTERVAL' in r.json()['errors']
    assert app.config['DAEMONSTATUS_REFRESH_INTERVAL'] == before


def test_settings_bootstrap_key_rejected(client):
    for key in ('DATABASE_URL', 'SCRAPYDWEB_PORT'):
        r = client.put('/api/settings', json={'settings': {key: 'x'}})
        assert r.status_code == 400, key
        assert key in r.json()['errors']


def test_settings_secret_keep(app, client):
    r = client.put('/api/settings', json={'settings': {'SLACK_TOKEN': 'tok-abc'}})
    assert r.status_code == 200
    assert app.config['SLACK_TOKEN'] == 'tok-abc'
    body = client.get('/api/settings/schema')
    assert 'tok-abc' not in body.text
    assert _field(body.json(), 'SLACK_TOKEN')['value'] == '__secret__'
    # empty / sentinel writes keep the stored secret
    for keep in ('', '__secret__'):
        r = client.put('/api/settings', json={'settings': {'SLACK_TOKEN': keep}})
        assert r.status_code == 200
        assert app.config['SLACK_TOKEN'] == 'tok-abc'
    client.put('/api/settings', json={'reset': ['SLACK_TOKEN']})


def test_settings_persist_across_app_recreate(client):
    r = client.put('/api/settings', json={'settings': {'JOBS_RELOAD_INTERVAL': 77}})
    assert r.status_code == 200
    from scrapydweb import create_app
    app2 = create_app({'TESTING': True, 'SCRAPYD_SERVERS': ['127.0.0.1:6800']})
    assert app2.config['JOBS_RELOAD_INTERVAL'] == 77
    assert app2.state.settings_sources['JOBS_RELOAD_INTERVAL'] == 'db'
    client.put('/api/settings', json={'reset': ['JOBS_RELOAD_INTERVAL']})


def test_settings_restart_flag(client):
    r = client.put('/api/settings', json={'settings': {'DEBUG': True}})
    assert r.status_code == 200
    js = r.json()
    assert js['results']['DEBUG'] == 'restart_required'
    assert js['restart_required'] is True
    assert 'DEBUG' in client.get('/api/settings/schema').json()['pending_restart']
    client.put('/api/settings', json={'reset': ['DEBUG']})


def test_settings_servers_structured_put(app, client):
    # __secret__ resolves against the existing auth keyed by host:port of node 1
    host, _, port = app.config['SCRAPYD_SERVERS'][0].partition(':')
    rows = [
        {'host': host, 'port': int(port), 'username': 'admin', 'password': '__secret__',
         'group': '', 'public_url': ''},
        {'host': '127.0.0.2', 'port': 6801, 'username': '', 'password': '', 'group': 'g2',
         'public_url': ''},
    ]
    r = client.put('/api/settings', json={'settings': {'SCRAPYD_SERVERS': rows,
                                                       'CHECK_SCRAPYD_SERVERS': False}})
    assert r.status_code == 200, r.text
    js = r.json()
    assert js['nodes_changed'] is True
    assert len(app.config['SCRAPYD_SERVERS']) == 2
    # __secret__ password resolved against the existing auth for 127.0.0.1:6800
    auths = app.config['SCRAPYD_SERVERS_AUTHS']
    assert ('admin', '12345') in auths
    nodes = client.get('/api/nodes').json()['nodes']
    assert len(nodes) == 2
    # restore the conftest layout for any later tests
    client.put('/api/settings', json={'reset': ['SCRAPYD_SERVERS', 'CHECK_SCRAPYD_SERVERS']})


def test_daemonstatus(client):
    js = client.get('/1/api/daemonstatus/').json()
    assert js['status'] == cst.OK
    for key in ['pending', 'running', 'finished']:
        assert key in js


def test_daemonstatus_fake_node(client):
    js = client.get('/2/api/daemonstatus/').json()
    assert js['status'] != cst.OK


def test_search(client):
    js = client.get('/1/search/?q=zzz-no-such-thing').json() if False else \
        client.get('/api/1/search/?q=zzz-no-such-thing').json()
    assert js['results'] == []


def test_tasks_history_json(client):
    js = client.get('/tasks/history/').json()
    assert js['status'] == cst.OK
    assert 'text' in js


def test_session_auth(app):
    from starlette.testclient import TestClient
    from tests.conftest import ADMIN_PASS, ADMIN_USER, authenticate
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)  # ensures the admin exists (also covers /setup once)
        me = c.get('/api/auth/me').json()
        assert me['authenticated'] is True and me['username'] == ADMIN_USER
        assert me['setup_required'] is False

        # second setup attempt is rejected
        r = c.post('/api/auth/setup', json={'username': 'x', 'password': 'password123'})
        assert r.status_code == 403

        # logout -> protected endpoints 401, SPA shell + auth endpoints stay open
        assert c.post('/api/auth/logout').status_code == 200
        assert c.get('/api/nodes').status_code == 401
        assert c.get('/1/api/daemonstatus/').status_code == 401
        assert c.get('/api/auth/me').status_code == 200
        assert c.get('/').status_code == 200

        # bad then good login
        r = c.post('/api/auth/login', json={'username': ADMIN_USER, 'password': 'wrong'})
        assert r.status_code == 401
        r = c.post('/api/auth/login', json={'username': ADMIN_USER, 'password': ADMIN_PASS})
        assert r.status_code == 200
        assert c.get('/api/nodes').status_code == 200

        # internal token header (poll subprocess / system jobs path)
        from scrapydweb.auth import INTERNAL_TOKEN_HEADER
        c.post('/api/auth/logout')
        r = c.get('/api/nodes', headers={INTERNAL_TOKEN_HEADER: app.config['_INTERNAL_TOKEN']})
        assert r.status_code == 200


def test_change_password(app):
    from starlette.testclient import TestClient
    from tests.conftest import ADMIN_PASS, ADMIN_USER, authenticate
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)
        r = c.post('/api/auth/password', json={'current': 'nope', 'new': 'newpass-123'})
        assert r.status_code == 400
        r = c.post('/api/auth/password', json={'current': ADMIN_PASS, 'new': 'newpass-123'})
        assert r.status_code == 200
        c.post('/api/auth/logout')
        assert c.post('/api/auth/login', json={'username': ADMIN_USER, 'password': ADMIN_PASS}).status_code == 401
        assert c.post('/api/auth/login', json={'username': ADMIN_USER, 'password': 'newpass-123'}).status_code == 200
        # restore for the rest of the session
        r = c.post('/api/auth/password', json={'current': 'newpass-123', 'new': ADMIN_PASS})
        assert r.status_code == 200
