# coding: utf-8
"""Fast schedule lifecycle against the fake scrapyd (no polling deadlines)."""
import os
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER
VERSION = cst.VERSION


def _deploy(client):
    egg = os.path.join(cst.ROOT_DIR, 'data', '%s.egg' % PROJECT)
    with open(egg, 'rb') as f:
        r = client.post('/1/deploy/upload/',
                        data={'project': PROJECT, 'version': VERSION},
                        files={'file': ('%s.egg' % PROJECT, f.read())})
    assert r.json()['status'] == cst.OK


def test_schedule_check_and_run_fast(app, client, fake_scrapyd):
    _deploy(client)
    jobid = 'fast-run-%s' % int(time.time())
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER, jobid=jobid,
        additional='-d setting=CLOSESPIDER_TIMEOUT=20 -d arg1=val1')).json()
    assert js['filename'].endswith('.pickle')
    assert 'curl' in js['cmd'] and jobid in js['cmd']

    js = client.post('/1/schedule/run/', data=dict(filename=js['filename'])).json()
    assert js['status'] == cst.OK, js
    assert js['jobid'] == jobid

    # instant_finish: the job is already finished on the fake
    row = next(j for j in client.get('/api/1/jobs/').json()['jobs'] if j['job'] == jobid)
    assert row['status'] == '2'
    assert row['version'] == VERSION  # resolved latest recorded at schedule time

    # code viewer serves the deployed egg
    js = client.get('/api/code/%s/%s/' % (PROJECT, VERSION)).json()
    assert js['status'] == cst.OK and js['files']

    # log + stats + collector
    js = client.get('/api/1/log/utf8/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK and js['version'] == VERSION

    from scrapydweb.services import logstats
    assert logstats.collect_all(app.config) >= 1
    row = next(j for j in client.get('/api/1/jobs/').json()['jobs'] if j['job'] == jobid)
    assert row['pages'] is not None and row['finish_reason'] == 'finished'


def test_schedule_xhr_records_version(client, fake_scrapyd):
    _deploy(client)
    jobid = 'fast-xhr-%s' % int(time.time())
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER, jobid=jobid)).json()
    js = client.post('/1/schedule/xhr/%s/' % js['filename']).json()
    assert js['status'] == cst.OK
    row = next(j for j in client.get('/api/1/jobs/').json()['jobs'] if j['job'] == jobid)
    assert row['version'] == VERSION


def test_schedule_run_error_status(client, fake_scrapyd):
    js = client.post('/1/schedule/check/', data=dict(
        project='NO_SUCH_PROJECT', _version=cst.DEFAULT_LATEST_VERSION,
        spider=SPIDER, jobid='fast-err')).json()
    js = client.post('/1/schedule/run/', data=dict(filename=js['filename'])).json()
    assert js['status'] == cst.ERROR


def test_schedule_run_multinode_first_node(client, fake_scrapyd):
    _deploy(client)
    jobid = 'fast-multi-%s' % int(time.time())
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER, jobid=jobid)).json()
    js = client.post('/1/schedule/run/', data={
        'filename': js['filename'], 'checked_amount': '2', '1': 'on', '2': 'on'}).json()
    assert js['status'] == cst.OK
    assert js['selected_nodes'] == [1, 2]
    assert js['first_selected_node'] == 1


def _add_task(client, name, minute, action='add_pause'):
    chk = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER, jobid='',
        trigger='cron', action=action, name=name, minute=minute)).json()
    js = client.post('/1/schedule/run/', data={
        'filename': chk['filename'], 'checked_amount': '1', '1': 'on'}).json()
    assert js['status'] == cst.OK, js
    return js['task_id']


def test_timer_task_edit_updates_in_place(client, fake_scrapyd):
    _deploy(client)
    task_id = _add_task(client, name='nightly', minute='0')
    before = client.get('/api/1/tasks/').json()
    row = next(t for t in before['tasks'] if t['id'] == task_id)
    assert row['name'] == 'nightly' and row['minute'] == '0'

    # edit: same task_id + replace_existing -> in-place update, not a new row
    chk = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER, jobid='',
        trigger='cron', action='add_pause', name='nightly-renamed', minute='30',
        task_id=str(task_id), replace_existing='True')).json()
    js = client.post('/1/schedule/run/', data={
        'filename': chk['filename'], 'checked_amount': '1', '1': 'on'}).json()
    assert js['status'] == cst.OK, js
    assert js['task_id'] == task_id  # same id -> updated, not created

    after = client.get('/api/1/tasks/').json()
    assert after['total'] == before['total']  # no new task row
    row = next(t for t in after['tasks'] if t['id'] == task_id)
    assert row['name'] == 'nightly-renamed'
    assert row['minute'] == '30'


def test_schedule_group_fans_out(client, fake_scrapyd):
    _deploy(client)
    js = client.post('/1/schedule/group/', json=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spiders=[SPIDER],
        nodes=[1], jobid='grp', settings=[{'key': 'CLOSESPIDER_TIMEOUT', 'value': '20'}],
        args={'crawl_item_ids': '["id-001"]'})).json()
    assert js['status'] == 'ok', js
    assert js['scheduled'] == 1 and js['total'] == 1
    r = js['results'][0]
    assert r['spider'] == SPIDER and r['status'] == cst.OK
    assert r['jobid'].startswith('grp_')
    # the job actually lands on the (fake) scrapyd
    assert any(j['job'] == r['jobid'] for j in client.get('/api/1/jobs/').json()['jobs'])


def test_schedule_group_cron_creates_tasks(client, fake_scrapyd):
    _deploy(client)
    js = client.post('/1/schedule/group/', json=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spiders=[SPIDER],
        nodes=[1], trigger='cron', action='add_pause', name='grp', minute='30')).json()
    assert js['status'] == 'ok' and js['mode'] == 'cron', js
    assert js['scheduled'] == 1
    # the timer task now exists
    tasks = client.get('/api/1/tasks/').json()['tasks']
    t = next(t for t in tasks if t['spider'] == SPIDER and t['name'] == 'grp_%s' % SPIDER)
    assert t['trigger'] == 'cron' and t['minute'] == '30'


def test_schedule_group_requires_spiders(client, fake_scrapyd):
    js = client.post('/1/schedule/group/', json=dict(project=PROJECT, spiders=[])).json()
    assert js['status'] == 'error'


def test_group_save_list_fire_delete(client, fake_scrapyd):
    _deploy(client)
    g = client.post('/api/groups', json=dict(
        name='g1', project=PROJECT, spiders=[SPIDER], nodes=[1],
        settings=[{'key': 'CLOSESPIDER_TIMEOUT', 'value': '20'}],
        args={'crawl_item_ids': '["id-001"]'})).json()
    assert g['status'] == 'ok', g
    gid = g['group']['id']
    assert g['group']['fire_path'] == '/api/groups/%s/fire' % gid
    # listed
    assert any(x['id'] == gid for x in client.get('/api/groups').json()['groups'])
    # fire by id -> schedules now
    js = client.post('/api/groups/%s/fire' % gid, json={}).json()
    assert js['status'] == 'ok' and js['scheduled'] == 1, js
    assert any(j['spider'] == SPIDER for j in client.get('/api/1/jobs/').json()['jobs'])
    # delete
    assert client.delete('/api/groups/%s' % gid).json()['status'] == 'ok'
    assert not any(x['id'] == gid for x in client.get('/api/groups').json()['groups'])


def test_group_schedule_creates_tasks(client, fake_scrapyd):
    _deploy(client)
    g = client.post('/api/groups', json=dict(
        name='gs', project=PROJECT, spiders=[SPIDER], nodes=[1])).json()
    gid = g['group']['id']
    js = client.post('/api/groups/%s/schedule' % gid,
                     json=dict(action='add_pause', minute='15')).json()
    assert js['status'] == 'ok' and js['scheduled'] == 1, js
    t = next(t for t in client.get('/api/1/tasks/').json()['tasks']
             if t['name'] == 'gs_%s' % SPIDER)
    assert t['trigger'] == 'cron' and t['minute'] == '15'


def test_group_call_args_override(client, fake_scrapyd):
    import json as _json
    _deploy(client)
    g = client.post('/api/groups', json=dict(
        name='ov', project=PROJECT, spiders=[SPIDER], nodes=[1], args={'base': '1'})).json()
    gid = g['group']['id']
    # schedule with a per-call arg -> task carries saved + override args
    js = client.post('/api/groups/%s/schedule' % gid,
                     json=dict(action='add_pause', minute='5',
                               args={'crawl_item_ids': '["id1"]'})).json()
    assert js['scheduled'] == 1, js
    t = next(t for t in client.get('/api/1/tasks/').json()['tasks']
             if t['name'] == 'ov_%s' % SPIDER)
    sa = _json.loads(t['settings_arguments'])
    assert sa.get('base') == '1' and sa.get('crawl_item_ids') == '["id1"]'
    # fire with a per-call arg
    f = client.post('/api/groups/%s/fire' % gid,
                    json=dict(args={'crawl_item_ids': '["id2"]'})).json()
    assert f['status'] == 'ok' and f['scheduled'] == 1


def test_group_requires_spiders(client):
    js = client.post('/api/groups', json=dict(name='bad', project=PROJECT, spiders=[])).json()
    assert js['status'] == 'error'


def test_group_fire_records_and_serves_args(client, fake_scrapyd):
    _deploy(client)
    g = client.post('/api/groups', json=dict(
        name='ar', project=PROJECT, spiders=[SPIDER], nodes=[1])).json()
    gid = g['group']['id']
    fired = client.post('/api/groups/%s/fire' % gid,
                        json=dict(args={'crawl_item_ids': '["id-1"]'})).json()
    assert fired['scheduled'] == 1
    jid = fired['results'][0]['jobid']
    jobs = client.get('/api/1/jobs/').json()['jobs']
    j = next(j for j in jobs if j['job'] == jid)
    assert j['args'].get('crawl_item_ids') == '["id-1"]'


def test_group_notify_config_persists(client):
    g = client.post('/api/groups', json=dict(
        name='nt', project=PROJECT, spiders=['x'], nodes=[1],
        notify_enabled=True, notify_channels=['slack', 'bogus'])).json()
    assert g['group']['notify_enabled'] is True
    assert g['group']['notify_channels'] == ['slack']  # unknown channel dropped


def test_finish_report_formatter():
    from scrapydweb.services.alerts import _finish_report

    class _Row:
        project, spider, job = 'p', 's', 'j'

    settings = {'URL_SCRAPYDWEB': 'http://x'}
    subj, text = _finish_report(settings, 1, _Row(), dict(
        finish_reason='finished', pages=5, items=2, runtime='0:01:00', log_categories={}))
    assert subj.startswith('✅') and 'items: 2' in text and 'pages: 5' in text
    subj, text = _finish_report(settings, 1, _Row(), dict(
        finish_reason='closespider_errorcount', pages=0, items=0,
        log_categories={'error_logs': {'count': 3}}))
    assert subj.startswith('❌') and 'errors: 3' in text


def test_schedule_history(client):
    r = client.get('/schedule/history/')
    assert r.status_code == 200
