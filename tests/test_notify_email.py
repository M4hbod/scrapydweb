# coding: utf-8
"""Email alert channel with smtplib monkeypatched (no network)."""
from scrapydweb.services import notify


def test_email_missing_password_error():
    ok, info = notify.send_email_alert({'EMAIL_PASSWORD': ''}, 'subj', 'text')
    assert ok is False
    assert 'EMAIL_PASSWORD' in info['error']


def test_email_sends_via_monkeypatched_smtp(monkeypatch):
    sent = {}

    class FakeSMTP(object):
        def __init__(self, server, port, timeout=30):
            sent['server'] = (server, port)

        def login(self, user, password):
            sent['login'] = (user, password)

        def sendmail(self, sender, recipients, msg):
            sent['mail'] = (sender, recipients)

        def quit(self):
            sent['quit'] = True

    import scrapydweb.utils.send_email as se
    monkeypatch.setattr(se.smtplib, 'SMTP_SSL', FakeSMTP)
    monkeypatch.setattr(se.smtplib, 'SMTP', FakeSMTP)

    settings = dict(EMAIL_PASSWORD='pw', EMAIL_USERNAME='u@example.com',
                    EMAIL_SENDER='u@example.com', EMAIL_RECIPIENTS=['r@example.com'],
                    SMTP_SERVER='smtp.example.com', SMTP_PORT=465, SMTP_OVER_SSL=True,
                    SMTP_CONNECTION_TIMEOUT=5)
    ok, info = notify.send_email_alert(settings, 'subj', 'text')
    assert ok is True, info
    assert sent['server'] == ('smtp.example.com', 465)
    assert sent['mail'][1] == ['r@example.com']


def test_dispatch_selects_enabled_channels(monkeypatch):
    calls = []
    monkeypatch.setitem(notify.CHANNELS, 'slack', lambda s, subject, text: calls.append('slack') or (True, {}))
    monkeypatch.setitem(notify.CHANNELS, 'telegram', lambda s, subject, text: calls.append('telegram') or (True, {}))
    monkeypatch.setitem(notify.CHANNELS, 'email', lambda s, subject, text: calls.append('email') or (True, {}))
    settings = dict(ENABLE_SLACK_ALERT=True, ENABLE_TELEGRAM_ALERT=False, ENABLE_EMAIL_ALERT=True)
    results = notify.dispatch(settings, 'subj', 'text')
    assert calls == ['slack', 'email']
    assert set(results) == {'slack', 'email'}


def test_slack_and_telegram_senders(monkeypatch):
    captured = []

    class FakeResp(object):
        def json(self):
            return {'ok': True}

    monkeypatch.setattr(notify.session, 'post',
                        lambda url, **kw: captured.append((url, kw)) or FakeResp())

    ok, _ = notify.send_slack({'SLACK_TOKEN': ''}, 'text')
    assert ok is False  # missing token

    ok, _ = notify.send_slack({'SLACK_TOKEN': 'xoxb-1', 'SLACK_CHANNEL': 'alerts'}, 'hello')
    assert ok is True
    url, kw = captured[-1]
    assert 'slack.com' in url
    assert kw['headers']['Authorization'] == 'Bearer xoxb-1'
    assert kw['data']['channel'] == 'alerts'

    ok, _ = notify.send_telegram({'TELEGRAM_TOKEN': 't', 'TELEGRAM_CHAT_ID': 0}, 'x')
    assert ok is False  # missing chat id
    ok, _ = notify.send_telegram({'TELEGRAM_TOKEN': 't', 'TELEGRAM_CHAT_ID': 42}, 'x')
    assert ok is True
    url, kw = captured[-1]
    assert 'api.telegram.org' in url and kw['data']['chat_id'] == 42
