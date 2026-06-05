# coding: utf-8
"""Runtime settings container for the FastAPI app.

Replaces Flask's ``app.config``. A plain mutable mapping seeded from
``scrapydweb.default_settings`` so tests can still mutate values at runtime
(``app.state.settings['SCRAPYD_SERVERS'] = ...``). Injected into routes via the
``get_settings`` dependency in ``scrapydweb.deps``.
"""
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

    def from_pyfile(self, path, silent=False):
        import types
        module = types.ModuleType('scrapydweb_user_settings')
        module.__file__ = path
        try:
            with open(path, 'rb') as f:
                exec(compile(f.read(), path, 'exec'), module.__dict__)
        except IOError:
            if silent:
                return False
            raise
        for key in dir(module):
            if key.isupper():
                self[key] = getattr(module, key)
        return True


def build_settings(overrides=None):
    settings = Settings(_defaults())
    settings.setdefault('SECRET_KEY', 'dev')
    if overrides:
        settings.update(overrides)
    return settings
