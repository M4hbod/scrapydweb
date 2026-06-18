# coding: utf-8
"""Notification channels (slack / telegram / email).

Pure sync functions over a settings dict -- shared by the settings-page test
buttons and the collector-driven alert engine.
"""
import logging

from ..common import session

logger = logging.getLogger(__name__)


def send_slack(settings, text):
    token = settings.get('SLACK_TOKEN', '')
    if not token:
        return False, {'error': 'SLACK_TOKEN is not set'}
    channel = settings.get('SLACK_CHANNEL', '') or 'general'
    try:
        # token goes in the Authorization header: form-body tokens are legacy
        # and rejected for granular bot tokens
        r = session.post('https://slack.com/api/chat.postMessage',
                         headers={'Authorization': 'Bearer %s' % token},
                         data=dict(channel=channel, text=text), timeout=30)
        js = r.json()
    except Exception as err:
        return False, {'error': str(err)}
    return bool(js.get('ok')), {k: v for k, v in js.items() if k != 'token'}


def send_telegram(settings, text):
    token = settings.get('TELEGRAM_TOKEN', '')
    chat_id = settings.get('TELEGRAM_CHAT_ID', 0)
    if not token:
        return False, {'error': 'TELEGRAM_TOKEN is not set'}
    if not chat_id:
        return False, {'error': 'TELEGRAM_CHAT_ID is not set'}
    try:
        r = session.post('https://api.telegram.org/bot%s/sendMessage' % token,
                         data=dict(chat_id=chat_id, text=text), timeout=30)
        js = r.json()
    except Exception as err:
        return False, {'error': str(err)}
    return bool(js.get('ok')), js


def send_email_alert(settings, subject, text):
    g = settings.get
    if not g('EMAIL_PASSWORD', ''):
        return False, {'error': 'EMAIL_PASSWORD is not set'}
    from ..utils.send_email import send_email
    sender = g('EMAIL_SENDER', '')
    kwargs = dict(
        email_username=g('EMAIL_USERNAME', '') or sender,
        email_password=g('EMAIL_PASSWORD', ''),
        email_sender=sender,
        email_recipients=g('EMAIL_RECIPIENTS', []),
        smtp_server=g('SMTP_SERVER', ''),
        smtp_port=g('SMTP_PORT', 0),
        smtp_over_ssl=g('SMTP_OVER_SSL', False),
        smtp_connection_timeout=g('SMTP_CONNECTION_TIMEOUT', 30),
        subject=subject,
        content=text,
    )
    result, reason = send_email(to_retry=True, **kwargs)
    return bool(result), {'reason': reason}


CHANNELS = {
    'slack': lambda s, subject, text: send_slack(s, text),
    'telegram': lambda s, subject, text: send_telegram(s, text),
    'email': send_email_alert,
}


def dispatch(settings, subject, text, channels=None):
    """Send the alert. With `channels` (a list subset of slack/telegram/email) send to
    exactly those; otherwise send to every channel whose ENABLE_<CH>_ALERT flag is on.
    Returns {channel: (ok, result)}."""
    results = {}
    for name, fn in CHANNELS.items():
        wanted = (name in channels) if channels else settings.get('ENABLE_%s_ALERT' % name.upper(), False)
        if wanted:
            try:
                results[name] = fn(settings, subject, text)
            except Exception as err:
                results[name] = (False, {'error': str(err)})
    for name, (ok, result) in results.items():
        (logger.info if ok else logger.warning)('alert via %s: ok=%s %s', name, ok, result)
    return results
