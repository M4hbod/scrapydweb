# coding: utf-8
"""CI deploy (token push + git), code viewer, download proxy, alert engine."""
import os
import subprocess
import shutil
import tempfile

import pytest

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _egg_bytes():
    with open(os.path.join(cst.ROOT_DIR, 'data', '%s.egg' % PROJECT), 'rb') as f:
        return f.read()


def test_deploy_push_token(app):
    app.config['DEPLOY_TOKEN'] = 'ci-token-123'
    try:
        # no token -> 401 (session cookie absent on raw TestClient? client IS logged in;
        # use a fresh unauthenticated client to prove the endpoint is gated)
        from starlette.testclient import TestClient
        from tests.conftest import authenticate
        with TestClient(app, follow_redirects=False) as anon:
            authenticate(anon)            # ensure the admin exists...
            anon.post('/api/auth/logout')  # ...then drop the session
            r = anon.post('/api/deploy/push',
                          data={'project': PROJECT, 'version': 'ci-1'},
                          files={'egg': ('p.egg', _egg_bytes())})
            assert r.status_code == 401
            r = anon.post('/api/deploy/push',
                          headers={'X-Deploy-Token': 'wrong'},
                          data={'project': PROJECT, 'version': 'ci-1'},
                          files={'egg': ('p.egg', _egg_bytes())})
            assert r.status_code == 401
            r = anon.post('/api/deploy/push',
                          headers={'X-Deploy-Token': 'ci-token-123'},
                          data={'project': PROJECT, 'version': 'ci-1'},
                          files={'egg': ('p.egg', _egg_bytes())})
            assert r.status_code == 200, r.text
            js = r.json()
            assert js['status'] == cst.OK and js['version'] == 'ci-1'
            authenticate(anon)
            anon.post('/1/api/delversion/%s/ci-1/' % PROJECT)
    finally:
        app.config['DEPLOY_TOKEN'] = ''


def test_deploy_push_multinode(app):
    """nodes='1,2': node 1 (live scrapyd) ok, node 2 (fake domain) error -> partial."""
    app.config['DEPLOY_TOKEN'] = 'ci-token-123'
    try:
        from starlette.testclient import TestClient
        from tests.conftest import authenticate
        with TestClient(app, follow_redirects=False) as anon:
            authenticate(anon)
            anon.post('/api/auth/logout')
            r = anon.post('/api/deploy/push',
                          headers={'X-Deploy-Token': 'ci-token-123'},
                          data={'project': PROJECT, 'version': 'ci-multi', 'nodes': '1,2'},
                          files={'egg': ('p.egg', _egg_bytes())})
            assert r.status_code == 200, r.text
            js = r.json()
            assert js['status'] == cst.OK and js['overall'] == 'partial'
            assert js['selected_nodes'] == [1, 2]
            by_node = {x['node']: x for x in js['results']}
            assert by_node[1]['status'] == cst.OK
            assert by_node[2]['status'] == 'error'
            authenticate(anon)
            # history records the deploy with per-node results
            hjs = anon.get('/api/deploy/history?project=%s' % PROJECT).json()
            assert hjs['status'] == cst.OK
            rec = next(x for x in hjs['records']
                       if x['version'] == 'ci-multi' and x['source'] == 'push')
            assert rec['status'] == 'partial' and rec['actor'] == 'deploy-token'
            assert {x['node'] for x in rec['results']} == {1, 2}
            anon.post('/1/api/delversion/%s/ci-multi/' % PROJECT)
    finally:
        app.config['DEPLOY_TOKEN'] = ''


def test_deploy_history_pagination(client):
    js = client.get('/api/deploy/history?per_page=5').json()
    assert js['status'] == cst.OK
    assert len(js['records']) <= 5
    ids = [r['id'] for r in js['records']]
    assert ids == sorted(ids, reverse=True)  # newest first


@pytest.mark.skipif(not shutil.which('git'), reason='git not installed')
def test_deploy_git(client):
    src_dir = os.path.join(cst.ROOT_DIR, 'data', PROJECT)
    tmp = tempfile.mkdtemp(prefix='swtest-git-')
    try:
        # build a local repo from the demo project (file:// allowed in TESTING)
        for cmd in (['git', 'init', '-q', '-b', 'main', tmp],):
            subprocess.run(cmd, check=True)
        subprocess.run(['cp', '-r', '%s/.' % src_dir, tmp], check=True)
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        subprocess.run(['git', '-C', tmp, 'add', '-A'], check=True, env=env)
        subprocess.run(['git', '-C', tmp, 'commit', '-qm', 'init'], check=True, env=env)

        r = client.post('/api/deploy/git', json={
            'repo': 'file://' + tmp, 'ref': 'main', 'project': PROJECT})
        assert r.status_code == 200, r.text
        js = r.json()
        assert js['status'] == cst.OK
        version = js['version']
        assert version  # short sha

        # code viewer reads the stored egg
        js = client.get('/api/code/%s/%s/' % (PROJECT, version)).json()
        assert js['status'] == cst.OK and js['files'], js
        py = next(f['path'] for f in js['files']
                  if f['path'].endswith('.py') and f['size'] > 50)
        js = client.get('/api/code/%s/%s/file?path=%s' % (PROJECT, version, py)).json()
        assert js['status'] == cst.OK and 'import' in js['text']
        # zip-slip / unknown path
        r = client.get('/api/code/%s/%s/file?path=../../etc/passwd' % (PROJECT, version))
        assert r.status_code == 404
        client.post('/1/api/delversion/%s/%s/' % (PROJECT, version))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_code_missing_egg(client):
    r = client.get('/api/code/no-such/v0/')
    assert r.status_code == 404
    assert 'outside scrapydweb' in r.json()['message']


def test_download_proxy(client):
    # the demo log is seeded into scrapyd's logs dir by setup_env
    r = client.get('/api/1/download/logs/%s/%s/%s' % (PROJECT, SPIDER, cst.DEMO_LOG))
    assert r.status_code == 200, r.text
    assert 'attachment' in r.headers.get('content-disposition', '')
    assert len(r.content) > 100
    # traversal guard (percent-encoded: httpx normalizes literal '..' client-side)
    r = client.get('/api/1/download/logs/%s/%s/%s' % ('%2e%2e', SPIDER, 'x.log'))
    assert r.status_code == 400


def test_alert_engine_evaluation(app, monkeypatch):
    from scrapydweb.services import alerts, notify

    sent = []
    cancels = []
    monkeypatch.setitem(notify.CHANNELS, 'slack',
                        lambda s, subject, text: (sent.append(text) or (True, {})))
    monkeypatch.setattr(alerts, '_cancel_job',
                        lambda server, auth, project, job, times=1: cancels.append(times))

    class Row:
        project, spider, job = 'p', 's', 'j'
        alert_state = None

    settings = dict(
        ALERT_WORKING_DAYS=list(range(1, 8)), ALERT_WORKING_HOURS=list(range(24)),
        ENABLE_SLACK_ALERT=True,
        LOG_CRITICAL_THRESHOLD=2, LOG_CRITICAL_TRIGGER_STOP=True,
        ON_JOB_FINISHED=True, URL_SCRAPYDWEB='http://x',
    )
    stats = dict(log_categories=dict(critical_logs=dict(count=5)),
                 finish_reason='finished', pages=1, items=1)

    row = Row()
    lines = alerts.evaluate_alerts(settings, '127.0.0.1:6800', 1, None, row, stats, running=True)
    assert any('CRITICAL: 5' in l for l in lines)
    assert cancels == [1]          # stop fired once
    assert len(sent) == 1          # one combined alert message

    # dedup: same stats again -> nothing new
    lines = alerts.evaluate_alerts(settings, '127.0.0.1:6800', 1, None, row, stats, running=True)
    assert lines == []
    assert len(sent) == 1

    # empty working hours = never notify
    row2 = Row()
    settings2 = dict(settings, ALERT_WORKING_HOURS=[])
    sent.clear()
    alerts.evaluate_alerts(settings2, '127.0.0.1:6800', 1, None, row2, stats, running=False)
    assert sent == []


def test_alert_test_endpoint(client):
    r = client.post('/api/alerts/test', json={'channel': 'slack'})
    js = r.json()
    assert js['status'] == 'error'  # SLACK_TOKEN unset
    assert 'SLACK_TOKEN' in str(js['result'])
    r = client.post('/api/alerts/test', json={'channel': 'bogus'})
    assert r.status_code == 400


def test_schedule_check_structured_json(client):
    """settings_json/args_json: digit keys + ' -d ' values survive; reserved arg keys skipped."""
    import json as _json
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version='default: the latest version', spider=SPIDER, jobid='structured-test',
        settings_json=_json.dumps([
            {'key': 'CLOSESPIDER_TIMEOUT', 'value': '60'},
            {'key': 'MY_KEY_2', 'value': 'x y -d z'},       # digit key + ' -d ' value: impossible via 'additional'
            {'key': 'bad-key', 'value': 'nope'},            # invalid key -> dropped
            {'key': 'EMPTY_VALUE', 'value': ''},            # empty value -> dropped
        ]),
        args_json=_json.dumps({'arg1': 'val1', 'project': 'evil', '1bad': 'nope'}),
    )).json()
    cmd = js['cmd']
    assert 'setting=CLOSESPIDER_TIMEOUT=60' in cmd
    assert 'setting=MY_KEY_2=x y -d z' in cmd
    assert 'bad-key' not in cmd and 'EMPTY_VALUE' not in cmd
    assert 'arg1=val1' in cmd
    assert 'evil' not in cmd        # reserved 'project' not overridden
    assert '1bad' not in cmd
    assert ('project=%s' % PROJECT) in cmd
