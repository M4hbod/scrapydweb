# coding: utf-8
"""Project registry: CRUD, per-project git deploy, GitHub webhook auto-deploy."""
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


def test_projects_crud(client):
    # create a webhook project -> secret generated
    r = client.post('/api/projects', json={
        'name': 'crud_proj', 'deploy_source': 'webhook',
        'repo_url': 'https://example.com/o/r.git', 'ref': 'dev', 'nodes': [1, 2]})
    assert r.status_code == 200, r.text
    p = r.json()['project']
    assert p['ref'] == 'dev' and p['default_nodes'] == [1, 2]
    assert len(p['webhook_secret']) == 64
    assert p['webhook_path'] == '/api/webhooks/github/%s' % p['id']
    pid = p['id']
    try:
        # a plain manual project needs no repo
        r = client.post('/api/projects', json={'name': 'manual_proj'})
        assert r.status_code == 200 and r.json()['project']['deploy_source'] == 'manual'
        client.delete('/api/projects/%s' % r.json()['project']['id'])
        # validation
        assert client.post('/api/projects', json={'name': ''}).status_code == 400
        r = client.post('/api/projects', json={
            'name': 'bad_url', 'deploy_source': 'git', 'repo_url': 'http://insecure'})
        assert r.status_code == 400 and 'https' in r.json()['message']
        # duplicate name
        r = client.post('/api/projects', json={'name': 'crud_proj'})
        assert r.status_code == 400 and 'already exists' in r.json()['message']
        # list
        names = [x['name'] for x in client.get('/api/projects').json()['projects']]
        assert 'crud_proj' in names
        # update + secret rotation
        r = client.put('/api/projects/%s' % pid,
                       json={'ref': 'main', 'enabled': False, 'rotate_secret': True})
        assert r.status_code == 200, r.text
        upd = r.json()['project']
        assert upd['ref'] == 'main' and upd['enabled'] is False
        assert upd['webhook_secret'] != p['webhook_secret']
        # disabled project -> webhook 404
        r = client.post('/api/webhooks/github/%s' % pid, content=b'{}',
                        headers={'X-Hub-Signature-256': 'sha256=00'})
        assert r.status_code == 404
        assert client.put('/api/projects/999999', json={'ref': 'x'}).status_code == 404
    finally:
        assert client.delete('/api/projects/%s' % pid).status_code == 200
    assert client.delete('/api/projects/%s' % pid).status_code == 404


def test_webhook_signature_and_events(client):
    r = client.post('/api/projects', json={
        'name': 'sig_proj', 'deploy_source': 'webhook',
        'repo_url': 'https://example.com/o/r.git', 'ref': 'main', 'nodes': [1]})
    p = r.json()['project']
    url, secret = p['webhook_path'], p['webhook_secret']
    try:
        body = json.dumps({'ref': 'refs/heads/main'}).encode()
        assert client.post(url, content=body).status_code == 401
        assert client.post(url, content=body,
                           headers={'X-Hub-Signature-256': 'sha256=deadbeef'}).status_code == 401
        r = client.post(url, content=b'{"zen": "ok"}',
                        headers={'X-Hub-Signature-256': _sign(secret, b'{"zen": "ok"}'),
                                 'X-GitHub-Event': 'ping'})
        assert r.status_code == 200 and r.json()['message'] == 'pong'
        r = client.post(url, content=body,
                        headers={'X-Hub-Signature-256': _sign(secret, body),
                                 'X-GitHub-Event': 'issues'})
        assert r.status_code == 200 and 'ignored event' in r.json()['message']
        other = json.dumps({'ref': 'refs/heads/feature'}).encode()
        r = client.post(url, content=other,
                        headers={'X-Hub-Signature-256': _sign(secret, other),
                                 'X-GitHub-Event': 'push'})
        assert r.status_code == 200 and 'ignored ref' in r.json()['message']
        assert client.post('/api/webhooks/github/999999', content=body,
                           headers={'X-Hub-Signature-256': _sign(secret, body)}).status_code == 404
    finally:
        client.delete('/api/projects/%s' % p['id'])


def test_webhook_needs_no_session(app):
    """The webhook path is exempt from session auth (HMAC replaces it)."""
    from starlette.testclient import TestClient
    from tests.conftest import authenticate
    with TestClient(app, follow_redirects=False) as anon:
        authenticate(anon)
        anon.post('/api/auth/logout')
        # 404 (unknown project), NOT 401 (unauthenticated)
        assert anon.post('/api/webhooks/github/999999', content=b'{}').status_code == 404
        # CRUD stays session-gated
        assert anon.get('/api/projects').status_code == 401


@pytest.mark.skipif(not shutil.which('git'), reason='git not installed')
def test_project_git_deploy(client):
    """A git project deploys via its saved config (POST /{id}/deploy)."""
    tmp = _make_local_repo()
    r = client.post('/api/projects', json={
        'name': PROJECT, 'deploy_source': 'git', 'repo_url': 'file://' + tmp,
        'ref': 'main', 'nodes': [1]})
    assert r.status_code == 200, r.text
    pid = r.json()['project']['id']
    version = None
    try:
        r = client.post('/api/projects/%s/deploy' % pid)
        assert r.status_code == 200, r.text
        js = r.json()
        assert js['status'] == cst.OK and js['results'][0]['status'] == cst.OK
        version = js['version']
        assert version
        code = client.get('/api/code/%s/%s/' % (PROJECT, version)).json()
        assert code['status'] == cst.OK and code['files']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        client.delete('/api/projects/%s' % pid)
        if version:
            client.post('/1/api/delversion/%s/%s/' % (PROJECT, version))


@pytest.mark.skipif(not shutil.which('git'), reason='git not installed')
def test_webhook_deploy_end_to_end(client):
    tmp = _make_local_repo()
    r = client.post('/api/projects', json={
        'name': PROJECT, 'deploy_source': 'webhook', 'repo_url': 'file://' + tmp,
        'ref': 'main', 'nodes': [1]})
    assert r.status_code == 200, r.text
    p = r.json()['project']
    version = None
    try:
        body = json.dumps({'ref': 'refs/heads/main'}).encode()
        r = client.post(p['webhook_path'], content=body,
                        headers={'X-Hub-Signature-256': _sign(p['webhook_secret'], body),
                                 'X-GitHub-Event': 'push'})
        assert r.status_code == 202, r.text
        record_id = r.json()['record_id']
        assert record_id
        # TestClient runs BackgroundTasks before returning -> record is final
        js = client.get('/api/deploy/history?project=%s' % PROJECT).json()
        assert js['status'] == cst.OK and js['total'] >= 1
        rec = next(x for x in js['records'] if x['id'] == record_id)
        assert rec['status'] == cst.OK, rec
        assert rec['source'] == 'webhook' and rec['actor'] == 'webhook:%s' % PROJECT
        assert rec['results'][0]['node'] == 1 and rec['results'][0]['status'] == cst.OK
        version = rec['version']
        assert version
        js = client.get('/api/code/%s/%s/' % (PROJECT, version)).json()
        assert js['status'] == cst.OK and js['files']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        client.delete('/api/projects/%s' % p['id'])
        if version:
            client.post('/1/api/delversion/%s/%s/' % (PROJECT, version))
