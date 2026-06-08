# coding: utf-8
"""/{n}/api/{opt} scrapyd JSON proxy (routers/api.py) against the fake."""
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _seed_project(fake_scrapyd):
    fake_scrapyd.state.projects.setdefault(PROJECT, {})['v1'] = b'egg'
    fake_scrapyd.state.spiders.setdefault(PROJECT, [SPIDER])


def test_proxy_listjobs(client, fake_scrapyd):
    _seed_project(fake_scrapyd)
    js = client.get('/1/api/listjobs/%s/' % PROJECT).json()
    assert js['status'] == cst.OK
    assert 'finished' in js and 'running' in js


def test_proxy_start_and_stop(client, fake_scrapyd):
    _seed_project(fake_scrapyd)
    js = client.post('/1/api/start/%s/%s/' % (PROJECT, SPIDER)).json()
    assert js['status'] == cst.OK
    jobid = js['jobid']
    js = client.post('/1/api/stop/%s/%s/' % (PROJECT, jobid)).json()
    assert js['status'] == cst.OK
    assert fake_scrapyd.state.counters['cancel'][(PROJECT, jobid)] == 1


def test_proxy_forcestop_calls_cancel_twice(client, fake_scrapyd):
    _seed_project(fake_scrapyd)
    jobid = 'force-%s' % int(time.time())
    fake_scrapyd.state.add_job(PROJECT, SPIDER, jobid, finished=False)
    js = client.post('/1/api/forcestop/%s/%s/' % (PROJECT, jobid)).json()
    assert js['status'] == cst.OK
    assert js['times'] == 2
    assert fake_scrapyd.state.counters['cancel'][(PROJECT, jobid)] == 2


def test_proxy_delproject(client, fake_scrapyd):
    fake_scrapyd.state.projects['tmp_proj'] = {'v1': b'egg'}
    js = client.post('/1/api/delproject/tmp_proj/').json()
    assert js['status'] == cst.OK
    js = client.get('/1/api/listprojects/').json()
    assert 'tmp_proj' not in js['projects']


def test_proxy_tip_no_active_project(client):
    js = client.get('/1/api/listversions/NO_SUCH_PROJECT/').json()
    assert js['status'] == cst.ERROR
    assert 'Projects page' in js['tip']


def test_proxy_tip_unreachable(client):
    js = client.get('/2/api/daemonstatus/').json()
    assert js['status'] == cst.ERROR
    assert 'accessable' in js['tip']
