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


def test_schedule_history(client):
    r = client.get('/schedule/history/')
    assert r.status_code == 200
