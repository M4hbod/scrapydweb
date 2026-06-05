# coding: utf-8
"""``url_for`` for the FastAPI app.

Derived from the registered Starlette routes (no separate registry). Mirrors
Flask's ``url_for`` semantics used across scrapydweb: pick the route variant
whose path params are satisfied by the provided non-None kwargs (most specific
first); remaining non-None kwargs become the query string. App code and tests
call the SAME function, so generated URLs are self-consistent.
"""
from urllib.parse import urlencode

from starlette.routing import NoMatchFound


def url_for(app, name, **values):
    if name == 'static':
        path = values.get('filename', values.get('path', ''))
        return str(app.url_path_for('static', path=path))

    if name == 'sendtextapi':
        # opt is a literal path prefix (slack/telegram/tg/email), not a path param.
        opt = values['opt']
        parts = ['/' + opt]
        ccs = values.get('channel_chatid_subject')
        text = values.get('text')
        if ccs is not None:
            parts.append(str(ccs))
        if text is not None:
            parts.append(str(text))
        return '/'.join(parts)

    provided = {k: v for k, v in values.items() if v is not None}
    routes = [r for r in app.routes
              if getattr(r, 'name', None) == name and hasattr(r, 'param_convertors')]
    routes.sort(key=lambda r: len(r.param_convertors), reverse=True)

    for route in routes:
        pnames = set(route.param_convertors)
        if pnames <= set(provided):
            path = str(app.url_path_for(name, **{k: provided[k] for k in pnames}))
            query = {k: v for k, v in provided.items() if k not in pnames}
            if query:
                path = '%s?%s' % (path, urlencode(query))
            return path

    raise NoMatchFound(name, values)


def safe_url_for(app, name, **values):
    """Tolerant url_for for in-page links to routes not yet ported (-> '#')."""
    try:
        return url_for(app, name, **values)
    except NoMatchFound:
        return '#'
