# coding: utf-8
"""Runtime settings container for the FastAPI app.

A plain mutable mapping seeded from ``scrapydweb.default_settings``; layered in
``create_app``: defaults < env overlays < DB-persisted settings < test overrides.
Injected into routes via the ``get_settings`` dependency in ``scrapydweb.deps``.
"""
import os

from . import default_settings


def _defaults():
    return {k: getattr(default_settings, k)
            for k in dir(default_settings) if k.isupper()}


class Settings(dict):
    """dict with attribute read access and Flask-config-ish helpers."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def from_object(self, obj):
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)

    def from_mapping(self, *args, **kwargs):
        self.update(*args, **kwargs)


def _env_bool(name):
    val = os.environ.get(name)
    return None if val is None else val.strip().lower() in ('1', 'true', 'yes', 'on')


def env_overrides():
    """Container-friendly env overlays (docker-compose sets these).

    These act as SEEDS: a value later edited in the settings UI (persisted to
    the DB) takes precedence over the env var.
    """
    out = {}
    servers = os.environ.get('SCRAPYD_SERVERS')
    if servers:
        # raw strings; check_scrapyd_servers owns the user:pass@host:port#group parsing
        out['SCRAPYD_SERVERS'] = [s.strip() for s in servers.split(',') if s.strip()]
    for key in ('ENABLE_SLACK_ALERT', 'ENABLE_TELEGRAM_ALERT', 'ENABLE_EMAIL_ALERT'):
        val = _env_bool(key)
        if val is not None:
            out[key] = val
    return out


def build_settings(overrides=None):
    settings = Settings(_defaults())
    settings.setdefault('SECRET_KEY', 'dev')
    if overrides:
        settings.update(overrides)
    return settings
