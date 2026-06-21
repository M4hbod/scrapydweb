# coding: utf-8
"""Prometheus /metrics exposition + auth."""


def _seed(app):
    from scrapydweb.db_sync import SyncSessionLocal
    from scrapydweb.models import JobStats
    server = app.state.settings['SCRAPYD_SERVERS'][0]
    with SyncSessionLocal() as s:
        s.add(JobStats(server=server, project='P', spider='sp', job='m1', items=10, pages=5,
                       finish_reason='finished', latest_log_time='2026-06-20 10:00:00'))
        s.add(JobStats(server=server, project='P', spider='sp', job='m2', items=0, pages=1,
                       finish_reason='closespider_errorcount', latest_log_time='2026-06-20 11:00:00'))
        s.commit()


def test_metrics_exposition(app, client):
    _seed(app)
    r = client.get('/metrics')
    assert r.status_code == 200
    assert 'text/plain' in r.headers['content-type']
    body = r.text
    assert 'scrapydweb_up 1' in body
    assert '# TYPE scrapydweb_items_scraped_total counter' in body
    assert 'scrapydweb_items_scraped_total{project="P",spider="sp"} 10' in body
    assert 'scrapydweb_pages_crawled_total{project="P",spider="sp"} 6' in body
    assert 'scrapydweb_jobs_finished_total{project="P",spider="sp",outcome="ok"} 1' in body
    assert 'scrapydweb_jobs_finished_total{project="P",spider="sp",outcome="failed"} 1' in body
    # the later run (m2) is the "last run": 0 items, not ok
    assert 'scrapydweb_spider_last_run_items{project="P",spider="sp"} 0' in body
    assert 'scrapydweb_spider_last_run_ok{project="P",spider="sp"} 0' in body
    assert 'scrapydweb_spider_last_finish_timestamp_seconds{project="P",spider="sp"}' in body


def test_metrics_requires_auth(client):
    client.cookies.clear()
    assert client.get('/metrics').status_code == 401
