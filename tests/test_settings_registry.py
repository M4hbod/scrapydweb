# coding: utf-8
"""Pure unit tests: settings_registry coerce + validators."""
from scrapydweb import settings_registry as reg


def test_coerce_bool():
    f = reg.REGISTRY['CHECK_SCRAPYD_SERVERS']
    assert reg.coerce(f, True) == (True, None)
    assert reg.coerce(f, 'yes')[1]  # error


def test_coerce_int():
    f = reg.REGISTRY['SMTP_PORT']
    value, err = reg.coerce(f, '465')
    assert (value, err) == (465, None)
    assert reg.coerce(f, 'abc')[1]


def test_coerce_list_int():
    f = reg.REGISTRY['ALERT_WORKING_DAYS']
    value, err = reg.coerce(f, [1, 2, 3])
    assert err is None and value == [1, 2, 3]
    _, err = reg.coerce(f, ['x'])
    assert err
    _, err = reg.coerce(f, 'not-a-list')
    assert err


def test_validator_days_hours():
    assert reg._v_days([1, 7], {}) is None
    assert reg._v_days([0], {})
    assert reg._v_hours([0, 23], {}) is None
    assert reg._v_hours([24], {})


def test_validator_email():
    assert reg._v_email_or_empty('', {}) is None
    assert reg._v_email_or_empty('a@b.co', {}) is None
    assert reg._v_email_or_empty('nope', {})
    assert reg._v_email_list(['a@b.co'], {}) is None
    assert reg._v_email_list(['bad'], {})


def test_validator_log_extensions():
    assert reg._v_log_extensions(['.log', '.gz'], {}) is None
    assert reg._v_log_extensions(['log'], {})


def test_validator_email_alert_requires_fields():
    assert reg._v_email_alert(True, {'ENABLE_EMAIL_ALERT': True})  # missing everything
    ok = {'ENABLE_EMAIL_ALERT': True, 'EMAIL_PASSWORD': 'x', 'EMAIL_SENDER': 'a@b.co',
          'EMAIL_RECIPIENTS': ['a@b.co'], 'SMTP_SERVER': 's', 'SMTP_PORT': 25}
    assert reg._v_email_alert(True, ok) is None


def test_default_for_matches_defaults():
    import scrapydweb.default_settings as ds
    assert reg.default_for('SCRAPYD_SERVERS') == ds.SCRAPYD_SERVERS
