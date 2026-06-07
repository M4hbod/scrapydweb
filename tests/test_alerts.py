# coding: utf-8
"""Alert pipeline (collector -> evaluate -> notify) + per-project/spider rules."""
import json
import time

from tests.utils import cst


def _settings(**overrides):
    base = dict(
        ALERT_WORKING_DAYS=list(range(1, 8)), ALERT_WORKING_HOURS=list(range(24)),
        ENABLE_SLACK_ALERT=True, ENABLE_TELEGRAM_ALERT=False, ENABLE_EMAIL_ALERT=False,
        URL_SCRAPYDWEB='http://x',
    )
    base.update(overrides)
    return base


class Row:
    def __init__(self, project='p', spider='s', job='j'):
        self.project, self.spider, self.job = project, spider, job
        self.alert_state = None


# ------------------------------------------------------------------ 5a: pipeline
def test_working_time_empty_disables(monkeypatch):
    from scrapydweb.services import alerts
    assert alerts._within_working_time(dict(ALERT_WORKING_DAYS=[], ALERT_WORKING_HOURS=[])) is False
    assert alerts._within_working_time(dict(ALERT_WORKING_DAYS=list(range(1, 8)),
                                            ALERT_WORKING_HOURS=[])) is False
    assert alerts._within_working_time(dict(ALERT_WORKING_DAYS=list(range(1, 8)),
                                            ALERT_WORKING_HOURS=list(range(24)))) is True


def test_alert_link_uses_public_url(monkeypatch):
    from scrapydweb.services import alerts, notify
    sent = []
    monkeypatch.setitem(notify.CHANNELS, 'slack',
                        lambda s, subject, text: (sent.append(text) or (True, {})))
    settings = _settings(URL_SCRAPYDWEB='https://scrapydweb.example.com',
                         ON_JOB_FINISHED=True)
    stats = dict(log_categories={}, finish_reason='finished', pages=1, items=1)
    alerts.evaluate_alerts(settings, '127.0.0.1:6800', 1, None, Row(), stats, running=False)
    assert sent and 'https://scrapydweb.example.com/log/1/stats/p/s/j' in sent[0]


def test_check_app_config_honors_public_url():
    """A user-set URL_SCRAPYDWEB must not be overwritten by the bind-derived one."""
    from scrapydweb.settings_registry import REGISTRY
    assert 'URL_SCRAPYDWEB' in REGISTRY  # editable on the settings page
    import scrapydweb.utils.check_app_config as cac
    import inspect
    src = inspect.getsource(cac)
    assert "if not config.get('URL_SCRAPYDWEB')" in src


def test_slack_uses_bearer_header(monkeypatch):
    from scrapydweb.services import notify
    captured = {}

    class R:
        def json(self):
            return {'ok': True}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured.update(url=url, headers=headers or {}, data=data or {})
        return R()

    monkeypatch.setattr(notify.session, 'post', fake_post)
    ok, _ = notify.send_slack(dict(SLACK_TOKEN='xoxb-123', SLACK_CHANNEL='ops'), 'hi')
    assert ok
    assert captured['headers'].get('Authorization') == 'Bearer xoxb-123'
    assert 'token' not in captured['data']  # form-body tokens are legacy


def test_realert_when_count_grows(monkeypatch):
    from scrapydweb.services import alerts, notify
    sent = []
    monkeypatch.setitem(notify.CHANNELS, 'slack',
                        lambda s, subject, text: (sent.append(text) or (True, {})))
    monkeypatch.setattr(alerts, '_cancel_job', lambda *a, **k: None)
    settings = _settings(LOG_ERROR_THRESHOLD=5)
    row = Row()
    stats5 = dict(log_categories=dict(error_logs=dict(count=5)), finish_reason='N/A')
    stats7 = dict(log_categories=dict(error_logs=dict(count=7)), finish_reason='N/A')
    assert alerts.evaluate_alerts(settings, 'srv', 1, None, row, stats5, running=True)
    assert not alerts.evaluate_alerts(settings, 'srv', 1, None, row, stats5, running=True)  # dedup
    assert alerts.evaluate_alerts(settings, 'srv', 1, None, row, stats7, running=True)  # re-alert
    assert len(sent) == 2


def test_forcestop_beats_stop(monkeypatch):
    from scrapydweb.services import alerts, notify
    cancels = []
    monkeypatch.setitem(notify.CHANNELS, 'slack', lambda s, subject, text: (True, {}))
    monkeypatch.setattr(alerts, '_cancel_job',
                        lambda server, auth, project, job, times=1: cancels.append(times))
    settings = _settings(
        LOG_ERROR_THRESHOLD=1, LOG_ERROR_TRIGGER_STOP=True,
        LOG_CRITICAL_THRESHOLD=1, LOG_CRITICAL_TRIGGER_FORCESTOP=True)
    stats = dict(log_categories=dict(error_logs=dict(count=3),
                                     critical_logs=dict(count=2)), finish_reason='N/A')
    alerts.evaluate_alerts(settings, 'srv', 1, None, Row(), stats, running=True)
    assert cancels == [2]  # forcestop = cancel twice


def test_running_interval_dedup_persists(monkeypatch):
    from scrapydweb.services import alerts, notify
    sent = []
    monkeypatch.setitem(notify.CHANNELS, 'slack',
                        lambda s, subject, text: (sent.append(text) or (True, {})))
    settings = _settings(ON_JOB_RUNNING_INTERVAL=3600)
    row = Row()
    stats = dict(log_categories={}, finish_reason='N/A', pages=1, items=1)
    assert alerts.evaluate_alerts(settings, 'srv', 1, None, row, stats, running=True)
    # state persisted on the row (as the collector would store it)
    assert json.loads(row.alert_state)['last_running_alert_ts'] <= time.time()
    assert not alerts.evaluate_alerts(settings, 'srv', 1, None, row, stats, running=True)
    assert len(sent) == 1


def test_dispatch_channel_isolation(monkeypatch):
    from scrapydweb.services import notify

    def boom(s, subject, text):
        raise RuntimeError('slack down')

    sent = []
    monkeypatch.setitem(notify.CHANNELS, 'slack', boom)
    monkeypatch.setitem(notify.CHANNELS, 'telegram',
                        lambda s, subject, text: (sent.append(text) or (True, {})))
    results = notify.dispatch(dict(ENABLE_SLACK_ALERT=True, ENABLE_TELEGRAM_ALERT=True),
                              'subj', 'text')
    assert results['slack'][0] is False and 'slack down' in str(results['slack'][1])
    assert results['telegram'][0] is True and sent == ['text']


# ------------------------------------------------------------------ 5b: rules
def test_effective_settings_precedence():
    from scrapydweb.services.alert_rules import effective_settings
    settings = dict(LOG_ERROR_THRESHOLD=0, ON_JOB_FINISHED=False,
                    ENABLE_SLACK_ALERT=True, ENABLE_TELEGRAM_ALERT=False,
                    ENABLE_EMAIL_ALERT=False)
    glob_rule = dict(id=1, project_pattern='proj*', spider_pattern='*',
                     thresholds={'ERROR': dict(threshold=10, action=None)},
                     on_finished=True, on_running_interval=None, channels=None)
    exact_rule = dict(id=2, project_pattern='proj1', spider_pattern='*',
                      thresholds={'ERROR': dict(threshold=3, action='stop')},
                      on_finished=None, on_running_interval=None, channels=['email'])

    # no match -> same object (global settings untouched)
    assert effective_settings(settings, [glob_rule, exact_rule], 'other', 's') is settings

    eff = effective_settings(settings, [glob_rule, exact_rule], 'proj2', 's')
    assert eff['LOG_ERROR_THRESHOLD'] == 10 and not eff['LOG_ERROR_TRIGGER_STOP']
    assert eff['ON_JOB_FINISHED'] is True

    # exact beats glob per field; non-null channels override the ENABLE_* flags
    eff = effective_settings(settings, [glob_rule, exact_rule], 'proj1', 's')
    assert eff['LOG_ERROR_THRESHOLD'] == 3 and eff['LOG_ERROR_TRIGGER_STOP'] is True
    assert eff['ON_JOB_FINISHED'] is True  # inherited from the broader rule
    assert eff['ENABLE_EMAIL_ALERT'] is True and eff['ENABLE_SLACK_ALERT'] is False


def test_rule_fires_where_global_would_not(monkeypatch):
    from scrapydweb.services import alerts, notify
    from scrapydweb.services.alert_rules import effective_settings
    sent = []
    monkeypatch.setitem(notify.CHANNELS, 'slack',
                        lambda s, subject, text: (sent.append(text) or (True, {})))
    monkeypatch.setattr(alerts, '_cancel_job', lambda *a, **k: None)
    settings = _settings()  # no global thresholds
    rule = dict(id=1, project_pattern='p', spider_pattern='*',
                thresholds={'CRITICAL': dict(threshold=1, action=None)},
                on_finished=None, on_running_interval=None, channels=None)
    stats = dict(log_categories=dict(critical_logs=dict(count=2)), finish_reason='N/A')
    # global settings alone: nothing fires
    assert not alerts.evaluate_alerts(settings, 'srv', 1, None, Row(), stats, running=True)
    # with the matching rule overlaid: alert fires
    eff = effective_settings(settings, [rule], 'p', 's')
    assert alerts.evaluate_alerts(eff, 'srv', 1, None, Row(), stats, running=True)
    assert len(sent) == 1


def test_rules_crud(client):
    r = client.post('/api/alerts/rules', json=dict(
        name='crit-stop', project_pattern='demo*', spider_pattern='*',
        thresholds={'CRITICAL': dict(threshold=2, action='forcestop')},
        on_finished=True, channels=['slack']))
    assert r.status_code == 200, r.text
    rule = r.json()['rule']
    rule_id = rule['id']
    assert rule['thresholds']['CRITICAL']['action'] == 'forcestop'
    assert rule['channels'] == ['slack'] and rule['enabled'] is True
    try:
        # validation
        assert client.post('/api/alerts/rules', json=dict(name='')).status_code == 400
        assert client.post('/api/alerts/rules', json=dict(
            name='x', thresholds={'BOGUS': dict(threshold=1)})).status_code == 400
        assert client.post('/api/alerts/rules', json=dict(
            name='x', thresholds={'ERROR': dict(threshold=-1)})).status_code == 400
        assert client.post('/api/alerts/rules', json=dict(
            name='x', channels=['pigeon'])).status_code == 400
        # list + update
        assert any(x['id'] == rule_id for x in client.get('/api/alerts/rules').json()['rules'])
        r = client.put('/api/alerts/rules/%s' % rule_id, json=dict(enabled=False, spider_pattern='sp?der'))
        assert r.status_code == 200 and r.json()['rule']['enabled'] is False
        assert client.put('/api/alerts/rules/999999', json=dict(enabled=False)).status_code == 404
        # preview resolves the effective settings
        client.put('/api/alerts/rules/%s' % rule_id, json=dict(enabled=True, spider_pattern='*'))
        js = client.post('/api/alerts/rules/preview', json=dict(project='demo1', spider='s')).json()
        assert rule_id in js['matched_rule_ids']
        assert js['effective']['LOG_CRITICAL_THRESHOLD'] == 2
        assert js['effective']['LOG_CRITICAL_TRIGGER_FORCESTOP'] is True
        js = client.post('/api/alerts/rules/preview', json=dict(project='nomatch', spider='s')).json()
        assert js['matched_rule_ids'] == []
    finally:
        assert client.delete('/api/alerts/rules/%s' % rule_id).status_code == 200
    assert client.delete('/api/alerts/rules/%s' % rule_id).status_code == 404


def test_collector_loads_rules(client, monkeypatch):
    """collect_all loads enabled rules once and feeds them to the evaluator."""
    from scrapydweb.services import logstats

    seen = {}

    def fake_collect_server(s, server, auth, extensions, settings=None, node=1, alert_rules=None):
        seen.setdefault('rules', alert_rules)
        return 0

    monkeypatch.setattr(logstats, '_collect_server', fake_collect_server)
    r = client.post('/api/alerts/rules', json=dict(name='collector-rule', project_pattern='*'))
    rule_id = r.json()['rule']['id']
    try:
        logstats.collect_all(dict(SCRAPYD_SERVERS=['127.0.0.1:6800']))
        assert any(x['id'] == rule_id for x in seen['rules'])
    finally:
        client.delete('/api/alerts/rules/%s' % rule_id)
