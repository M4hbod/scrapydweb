# coding: utf-8
"""Auth edge paths: bad login, setup-once, logout, password change."""
from starlette.testclient import TestClient

from tests.conftest import ADMIN_PASS, ADMIN_USER, authenticate


def test_login_wrong_password(app):
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)  # ensure the admin exists
        c.post('/api/auth/logout')
        r = c.post('/api/auth/login', json={'username': ADMIN_USER, 'password': 'wrong'})
        assert r.status_code == 401
        assert c.get('/api/auth/me').json()['authenticated'] is False


def test_setup_only_once(app):
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)
        r = c.post('/api/auth/setup', json={'username': 'second', 'password': 'whatever123'})
        assert r.status_code in (400, 403, 409)


def test_logout_clears_session(app):
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)
        assert c.get('/api/auth/me').json()['authenticated'] is True
        c.post('/api/auth/logout')
        assert c.get('/api/auth/me').json()['authenticated'] is False


def test_change_password_flow(app):
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)
        # wrong current password rejected
        r = c.post('/api/auth/password', json={'current': 'nope', 'new': 'newpass123'})
        assert r.status_code == 400
        # too-short new password rejected
        r = c.post('/api/auth/password', json={'current': ADMIN_PASS, 'new': 'short'})
        assert r.status_code == 400
        # correct change, then restore
        r = c.post('/api/auth/password', json={'current': ADMIN_PASS, 'new': 'temp-pass-123'})
        assert r.status_code == 200, r.text
        c.post('/api/auth/logout')
        r = c.post('/api/auth/login', json={'username': ADMIN_USER, 'password': 'temp-pass-123'})
        assert r.status_code == 200
        r = c.post('/api/auth/password', json={'current': 'temp-pass-123', 'new': ADMIN_PASS})
        assert r.status_code == 200


def test_unauthenticated_api_401(app):
    with TestClient(app, follow_redirects=False) as c:
        authenticate(c)  # creates the admin so setup_required is False
        c.post('/api/auth/logout')
        assert c.get('/api/nodes').status_code == 401
