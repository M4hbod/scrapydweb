# coding: utf-8
"""GitHub webhook auto-deploy: repo CRUD, HMAC verification, end-to-end deploy."""
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile

import pytest

from tests.utils import cst

PROJECT = cst.PROJECT


def _sign(secret, body):
    return 'sha256=' + hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


def _make_local_repo():
    """Local git repo built from the demo project (file:// allowed in TESTING)."""
    src_dir = os.path.join(cst.ROOT_DIR, 'data', PROJECT)
    tmp = tempfile.mkdtemp(prefix='swtest-webhook-')
    subprocess.run(['git', 'init', '-q', '-b', 'main', tmp], check=True)
    subprocess.run(['cp', '-r', '%s/.' % src_dir, tmp], check=True)
    env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
               GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
    subprocess.run(['git', '-C', tmp, 'add', '-A'], check=True, env=env)
    subprocess.run(['git', '-C', tmp, 'commit', '-qm', 'init'], check=True, env=env)
    return tmp


def test_repos_crud(client):
    # create
    r = client.post('/api/deploy/repos', json={
        'name': 'crud-repo', 'repo_url': 'https://example.com/o/r.git',
        'ref': 'dev', 'project': PROJECT, 'nodes': [1, 2]})
    assert r.status_code == 200, r.text
    repo = r.json()['repo']
    assert repo['ref'] == 'dev' and repo['nodes'] == [1, 2]
    assert len(repo['webhook_secret']) == 64
    assert repo['webhook_path'] == '/api/webhooks/github/%s' % repo['id']
    repo_id = repo['id']
    try:
        # validation
        r = client.post('/api/deploy/repos', json={'name': '', 'repo_url': 'x', 'project': 'p'})
        assert r.status_code == 400
        r = client.post('/api/deploy/repos', json={
            'name': 'bad-url', 'repo_url': 'http://insecure', 'project': 'p'})
        assert r.status_code == 400 and 'https' in r.json()['message']
        # duplicate name
        r = client.post('/api/deploy/repos', json={
            'name': 'crud-repo', 'repo_url': 'https://example.com/o/r.git', 'project': 'p'})
        assert r.status_code == 400 and 'already exists' in r.json()['message']
        # list
        repos = client.get('/api/deploy/repos').json()['repos']
        assert any(x['id'] == repo_id for x in repos)
        # update + secret rotation
        r = client.put('/api/deploy/repos/%s' % repo_id,
                       json={'ref': 'main', 'enabled': False, 'rotate_secret': True})
        assert r.status_code == 200, r.text
        updated = r.json()['repo']
        assert updated['ref'] == 'main' and updated['enabled'] is False
        assert updated['webhook_secret'] != repo['webhook_secret']
        # disabled repo -> webhook 404
        r = client.post('/api/webhooks/github/%s' % repo_id, content=b'{}',
                        headers={'X-Hub-Signature-256': 'sha256=00'})
        assert r.status_code == 404
        r = client.put('/api/deploy/repos/999999', json={'ref': 'x'})
        assert r.status_code == 404
    finally:
        assert client.delete('/api/deploy/repos/%s' % repo_id).status_code == 200
    assert client.delete('/api/deploy/repos/%s' % repo_id).status_code == 404


def test_webhook_signature_and_events(client):
    r = client.post('/api/deploy/repos', json={
        'name': 'sig-repo', 'repo_url': 'https://example.com/o/r.git',
        'ref': 'main', 'project': PROJECT, 'nodes': [1]})
    repo = r.json()['repo']
    url = repo['webhook_path']
    secret = repo['webhook_secret']
    try:
        body = json.dumps({'ref': 'refs/heads/main'}).encode()
        # missing / wrong signature
        assert client.post(url, content=body).status_code == 401
        assert client.post(url, content=body,
                           headers={'X-Hub-Signature-256': 'sha256=deadbeef'}).status_code == 401
        # ping -> pong
        r = client.post(url, content=b'{"zen": "ok"}',
                        headers={'X-Hub-Signature-256': _sign(secret, b'{"zen": "ok"}'),
                                 'X-GitHub-Event': 'ping'})
        assert r.status_code == 200 and r.json()['message'] == 'pong'
        # non-push event ignored
        r = client.post(url, content=body,
                        headers={'X-Hub-Signature-256': _sign(secret, body),
                                 'X-GitHub-Event': 'issues'})
        assert r.status_code == 200 and 'ignored event' in r.json()['message']
        # push to another branch ignored
        other = json.dumps({'ref': 'refs/heads/feature'}).encode()
        r = client.post(url, content=other,
                        headers={'X-Hub-Signature-256': _sign(secret, other),
                                 'X-GitHub-Event': 'push'})
        assert r.status_code == 200 and 'ignored ref' in r.json()['message']
        # unknown repo id
        assert client.post('/api/webhooks/github/999999', content=body,
                           headers={'X-Hub-Signature-256': _sign(secret, body)}).status_code == 404
    finally:
        client.delete('/api/deploy/repos/%s' % repo['id'])


def test_webhook_needs_no_session(app):
    """The webhook path is exempt from session auth (HMAC replaces it)."""
    from starlette.testclient import TestClient
    from tests.conftest import authenticate
    with TestClient(app, follow_redirects=False) as anon:
        authenticate(anon)             # ensure the admin exists...
        anon.post('/api/auth/logout')  # ...then drop the session
        # 404 (unknown repo), NOT 401 (unauthenticated)
        r = anon.post('/api/webhooks/github/999999', content=b'{}')
        assert r.status_code == 404
        # CRUD stays session-gated
        assert anon.get('/api/deploy/repos').status_code == 401


@pytest.mark.skipif(not shutil.which('git'), reason='git not installed')
def test_webhook_deploy_end_to_end(client):
    tmp = _make_local_repo()
    r = client.post('/api/deploy/repos', json={
        'name': 'e2e-repo', 'repo_url': 'file://' + tmp,
        'ref': 'main', 'project': PROJECT, 'nodes': [1]})
    assert r.status_code == 200, r.text
    repo = r.json()['repo']
    version = None
    try:
        body = json.dumps({'ref': 'refs/heads/main'}).encode()
        r = client.post(repo['webhook_path'], content=body,
                        headers={'X-Hub-Signature-256': _sign(repo['webhook_secret'], body),
                                 'X-GitHub-Event': 'push'})
        assert r.status_code == 202, r.text
        record_id = r.json()['record_id']
        assert record_id
        # TestClient runs BackgroundTasks before returning -> record is final
        js = client.get('/api/deploy/history?repo_id=%s' % repo['id']).json()
        assert js['status'] == cst.OK and js['total'] >= 1
        rec = next(x for x in js['records'] if x['id'] == record_id)
        assert rec['status'] == cst.OK, rec
        assert rec['source'] == 'webhook' and rec['actor'] == 'webhook:e2e-repo'
        assert rec['results'][0]['node'] == 1 and rec['results'][0]['status'] == cst.OK
        version = rec['version']
        assert version  # short commit sha
        # deployed egg is browsable in the code viewer
        js = client.get('/api/code/%s/%s/' % (PROJECT, version)).json()
        assert js['status'] == cst.OK and js['files']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        client.delete('/api/deploy/repos/%s' % repo['id'])
        if version:
            client.post('/1/api/delversion/%s/%s/' % (PROJECT, version))
