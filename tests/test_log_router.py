# coding: utf-8
"""Log viewer endpoints (routers/log.py) against the fake scrapyd."""
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _schedule(client, fake_scrapyd, jobid, finished=True):
    fake_scrapyd.state.projects.setdefault(PROJECT, {})['v1'] = b'egg'
    fake_scrapyd.state.spiders.setdefault(PROJECT, [SPIDER])
    fake_scrapyd.state.add_job(PROJECT, SPIDER, jobid, finished=finished)
    return jobid


def test_log_utf8_finished(client, fake_scrapyd):
    jobid = _schedule(client, fake_scrapyd, 'log-utf8-%s' % int(time.time()))
    js = client.get('/api/1/log/utf8/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert js['finished'] is True
    assert 'scrapy.core.engine' in js['text']


def test_log_stats_parsed_on_the_fly(client, fake_scrapyd):
    jobid = _schedule(client, fake_scrapyd, 'log-stats-%s' % int(time.time()))
    js = client.get('/api/1/log/stats/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert 'log_categories' in js['stats']
    assert js['logparser_valid'] is False  # no collector row yet


def test_log_stats_from_collector(app, client, fake_scrapyd):
    jobid = _schedule(client, fake_scrapyd, 'log-coll-%s' % int(time.time()))
    from scrapydweb.services import logstats
    assert logstats.collect_all(app.config) >= 1
    js = client.get('/api/1/log/stats/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert js['logparser_valid'] is True
    assert js['stats']['pages'] is not None


def test_log_utf8_running_job(client, fake_scrapyd):
    jobid = _schedule(client, fake_scrapyd, 'log-run-%s' % int(time.time()), finished=False)
    js = client.get('/api/1/log/utf8/%s/%s/%s/' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert js['finished'] is False


def test_log_missing_returns_error(client):
    js = client.get('/api/1/log/utf8/%s/%s/no-such-job/' % (PROJECT, SPIDER)).json()
    assert js['status'] == cst.ERROR


def test_log_report(client, fake_scrapyd):
    jobid = _schedule(client, fake_scrapyd, 'log-report-%s' % int(time.time()))
    js = client.get('/1/log/report/%s/%s/%s/' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert 'log_categories' in js


def test_log_unreachable_node(client):
    js = client.get('/api/2/log/utf8/%s/%s/whatever/' % (PROJECT, SPIDER)).json()
    assert js['status'] == cst.ERROR
