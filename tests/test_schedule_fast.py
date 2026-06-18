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
        args={'crawl_imdb_ids': '["tt0111161"]'})).json()
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


def test_schedule_history(client):
    r = client.get('/schedule/history/')
    assert r.status_code == 200
