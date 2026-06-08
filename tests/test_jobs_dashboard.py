# coding: utf-8
"""api_jobs persistence + dashboard aggregation + search against the fake scrapyd."""
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _seed(fake_scrapyd, jobid, finished=True):
    fake_scrapyd.state.projects.setdefault(PROJECT, {})['v1'] = b'egg'
    fake_scrapyd.state.spiders.setdefault(PROJECT, [SPIDER])
    fake_scrapyd.state.add_job(PROJECT, SPIDER, jobid, finished=finished)


def test_jobs_listing_and_persist(client, fake_scrapyd):
    base = 'jobs-%s' % int(time.time())
    for i in range(3):
        _seed(fake_scrapyd, '%s-%d' % (base, i))
    js = client.get('/api/1/jobs/').json()
    assert js['status'] == cst.OK
    rows = [j for j in js['jobs'] if j['job'].startswith(base)]
    assert len(rows) == 3
    assert all(r['status'] == '2' for r in rows)
    assert all(r['href_log'].startswith('/logs/') for r in rows)


def test_jobs_running_then_finished(client, fake_scrapyd):
    jobid = 'jobs-trans-%s' % int(time.time())
    _seed(fake_scrapyd, jobid, finished=False)
    row = next(j for j in client.get('/api/1/jobs/').json()['jobs'] if j['job'] == jobid)
    assert row['status'] == '1'
    fake_scrapyd.state.finish_job(PROJECT, SPIDER, jobid)
    row = next(j for j in client.get('/api/1/jobs/').json()['jobs'] if j['job'] == jobid)
    assert row['status'] == '2'
    assert row['finish']


def test_jobs_pagination(client, fake_scrapyd):
    _seed(fake_scrapyd, 'jobs-page-%s' % int(time.time()))
    js = client.get('/api/1/jobs/?per_page=1&page=1').json()
    assert js['status'] == cst.OK
    assert len(js['jobs']) == 1
    assert js['pages'] >= 1


def test_jobs_unreachable_node(client):
    js = client.get('/api/2/jobs/').json()
    assert js['status'] == cst.ERROR


def test_jobs_bad_node_400(client):
    r = client.get('/api/99/jobs/')
    assert r.status_code == 400
    assert r.json()['status'] == cst.ERROR


def test_dashboard_aggregates(client, fake_scrapyd):
    _seed(fake_scrapyd, 'dash-%s' % int(time.time()))
    client.get('/api/1/jobs/')  # persist
    js = client.get('/api/dashboard').json()
    d = js['dashboard']
    assert d['kpi']['finished'] >= 1
    assert len(d['nodes']) == 2
    assert isinstance(d['throughput'], list)
    assert any(e['job'].startswith('dash-') for e in d['activity'])


def test_search_jobs(client, fake_scrapyd):
    jobid = 'searchme-%s' % int(time.time())
    _seed(fake_scrapyd, jobid)
    client.get('/api/1/jobs/')  # persist
    js = client.get('/api/1/search/?q=searchme').json()
    assert any(jobid == r['job'] for r in js['results'])
    js = client.get('/api/1/search/?q=').json()
    assert js['results'] == []
