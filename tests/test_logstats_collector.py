# coding: utf-8
"""Central stats collector (services/logstats.py) against the fake scrapyd."""
import json
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _seed(fake_scrapyd, jobid, finished=True, log=None):
    fake_scrapyd.state.projects.setdefault(PROJECT, {})['v1'] = b'egg'
    fake_scrapyd.state.spiders.setdefault(PROJECT, [SPIDER])
    fake_scrapyd.state.add_job(PROJECT, SPIDER, jobid, finished=finished, log=log)


def _row(server, jobid):
    from scrapydweb.db_sync import SyncSessionLocal
    from scrapydweb.models import JobStats
    with SyncSessionLocal() as s:
        return s.query(JobStats).filter_by(server=server, job=jobid).first()


def test_collect_creates_jobstats(app, client, fake_scrapyd):
    jobid = 'coll-%s' % int(time.time())
    _seed(fake_scrapyd, jobid)
    from scrapydweb.services import logstats
    assert logstats.collect_all(app.config) >= 1
    row = _row(fake_scrapyd.address, jobid)
    assert row is not None
    assert row.pages is not None and row.items is not None
    assert row.finish_reason == 'finished'
    assert json.loads(row.stats_json)['log_categories']


def test_collect_skips_unchanged(app, client, fake_scrapyd):
    fake_scrapyd.state.reset()  # other tests' running jobs would re-parse every cycle
    jobid = 'coll-skip-%s' % int(time.time())
    _seed(fake_scrapyd, jobid)
    from scrapydweb.services import logstats
    assert logstats.collect_all(app.config) >= 1
    assert logstats.collect_all(app.config) == 0  # size unchanged + finished


def test_unfinished_to_finished_transition(app, client, fake_scrapyd):
    jobid = 'coll-trans-%s' % int(time.time())
    _seed(fake_scrapyd, jobid, finished=False)
    from scrapydweb.services import logstats
    logstats.collect_all(app.config)
    row = _row(fake_scrapyd.address, jobid)
    assert row.finish_reason == 'N/A'
    fake_scrapyd.state.finish_job(PROJECT, SPIDER, jobid)
    logstats.collect_all(app.config)
    row = _row(fake_scrapyd.address, jobid)
    assert row.finish_reason == 'finished'


def test_probe_naive_server_reuses_body(app, client, fake_scrapyd):
    """Server ignoring Range returns the full body; the collector must not re-fetch."""
    fake_scrapyd.state.reset()  # isolate the request counter to one job
    jobid = 'coll-naive-%s' % int(time.time())
    _seed(fake_scrapyd, jobid)
    fake_scrapyd.state.naive_range = True
    try:
        from scrapydweb.services import logstats
        before = fake_scrapyd.state.counters['requests'].get('logs', 0)
        assert logstats.collect_all(app.config) >= 1
        after = fake_scrapyd.state.counters['requests']['logs']
        # exactly one /logs request: the probe body was reused, no second fetch
        assert after - before == 1
    finally:
        fake_scrapyd.state.naive_range = False


def test_missing_log_skipped(app, client, fake_scrapyd):
    jobid = 'coll-nolog-%s' % int(time.time())
    _seed(fake_scrapyd, jobid)
    fake_scrapyd.state.logs.pop((PROJECT, SPIDER, jobid))
    from scrapydweb.services import logstats
    logstats.collect_all(app.config)
    assert _row(fake_scrapyd.address, jobid) is None


def test_alert_fires_and_cancels(app, client, fake_scrapyd, monkeypatch):
    """ERROR threshold on a running job triggers dispatch + cancel.json; dedup holds."""
    jobid = 'coll-alert-%s' % int(time.time())
    errorful = fake_scrapyd.state.unfinished_log + (
        '\n2018-10-23 18:29:41 [test] ERROR: boom\n2018-10-23 18:29:42 [test] ERROR: boom2\n')
    _seed(fake_scrapyd, jobid, finished=False, log=errorful)

    sent = []
    from scrapydweb.services import notify
    monkeypatch.setattr(notify, 'dispatch', lambda s, subject, text: sent.append(subject) or {})

    config = dict(app.config)
    config.update(LOG_ERROR_THRESHOLD=1, LOG_ERROR_TRIGGER_STOP=True,
                  ON_JOB_RUNNING_INTERVAL=0, ENABLE_SLACK_ALERT=True)
    from scrapydweb.services import logstats
    logstats.collect_all(config)
    assert sent, 'alert never dispatched'
    assert fake_scrapyd.state.counters['cancel'].get((PROJECT, jobid), 0) >= 1
    # dedup: same counts -> no new alert. cancel flipped the job to finished w/
    # the canned finished log, so re-collect parses it without re-alerting on ERROR
    n = len(sent)
    logstats.collect_all(config)
    assert len(sent) == n
