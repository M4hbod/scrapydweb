# coding: utf-8
"""Jinja2 templating (replaces Flask render_template + context processors + g).

A single Jinja ``Environment`` over the existing ``templates/`` dir, with the
same custom ``{{ `` / `` }}`` delimiters and ``regex_replace`` filter. The base
context (static asset URLs, version vars, scrapyd-server vars, and the per-request
``g`` namespace of menu URLs) is assembled here and merged with each page's
context. ``url_for`` and ``flash`` come from ``scrapydweb.urls`` / per-request.
"""
import re
from types import SimpleNamespace

import jinja2
from logparser import __version__ as LOGPARSER_VERSION
from starlette.responses import HTMLResponse

from .__version__ import __url__, __version__
from .scheduler import STATE_PAUSED, STATE_RUNNING, safe_get_jobs, scheduler
from .urls import url_for
from .vars import PYTHON_VERSION, ROOT_DIR, SCRAPY_VERSION, SCRAPYD_VERSION

STATIC_VERSION = 'v' + __version__.replace('.', '')

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(ROOT_DIR + '/templates'),
    autoescape=jinja2.select_autoescape(['html', 'xml']),
    variable_start_string='{{ ',
    variable_end_string=' }}',
    enable_async=False,
)
env.filters['regex_replace'] = lambda s, find, replace: re.sub(find, replace, s)


def _static(app):
    def s(filename):
        return url_for(app, 'static', filename='%s/%s' % (STATIC_VERSION, filename))
    return dict(
        static_css_dropdown=s('css/dropdown.css'),
        static_css_dropdown_mobileui=s('css/dropdown_mobileui.css'),
        static_css_icon_upload_icon_right=s('css/icon_upload_icon_right.css'),
        static_css_multinode=s('css/multinode.css'),
        static_css_stacktable=s('css/stacktable.css'),
        static_css_stats=s('css/stats.css'),
        static_css_style=s('css/style.css'),
        static_css_style_mobileui=s('css/style_mobileui.css'),
        static_css_utf8=s('css/utf8.css'),
        static_css_utf8_mobileui=s('css/utf8_mobileui.css'),
        static_css_element_ui_index=s('element-ui@2.4.6/lib/theme-chalk/index.css'),
        static_js_element_ui_index=s('element-ui@2.4.6/lib/index.js'),
        static_js_common=s('js/common.js'),
        static_js_echarts_min=s('js/echarts.min.js'),
        static_js_icons_menu=s('js/icons_menu.js'),
        static_js_github_buttons=s('js/github_buttons.js'),
        static_js_jquery_min=s('js/jquery.min.js'),
        static_js_multinode=s('js/multinode.js'),
        static_js_stacktable=s('js/stacktable.js'),
        static_js_stats=s('js/stats.js'),
        static_js_vue_min=s('js/vue.min.js'),
        static_icon=s('icon/fav.ico'),
        static_icon_shortcut=s('icon/fav.ico'),
        static_icon_apple_touch=s('icon/spiderman.png'),
    )


def _version_vars():
    return dict(
        CHECK_LATEST_VERSION_FREQ=100,
        GITHUB_URL=__url__,
        PYTHON_VERSION=PYTHON_VERSION,
        SCRAPYDWEB_VERSION=__version__,
        SCRAPY_VERSION=SCRAPY_VERSION,
        SCRAPYD_VERSION=SCRAPYD_VERSION,
        LOGPARSER_VERSION=LOGPARSER_VERSION,
    )


def _server_vars(settings):
    servers = settings.get('SCRAPYD_SERVERS', []) or ['127.0.0.1:6800']
    amount = len(servers)
    return dict(
        SCRAPYD_SERVERS=servers,
        SCRAPYD_SERVERS_AMOUNT=amount,
        SCRAPYD_SERVERS_GROUPS=settings.get('SCRAPYD_SERVERS_GROUPS', []) or [''],
        SCRAPYD_SERVERS_AUTHS=settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None],
        SCRAPYD_SERVERS_PUBLIC_URLS=settings.get('SCRAPYD_SERVERS_PUBLIC_URLS', None) or [''] * amount,
        DAEMONSTATUS_REFRESH_INTERVAL=settings.get('DAEMONSTATUS_REFRESH_INTERVAL', 10),
        ENABLE_AUTH=settings.get('ENABLE_AUTH', False),
        SHOW_SCRAPYD_ITEMS=settings.get('SHOW_SCRAPYD_ITEMS', True),
    )


_MENU = ['servers', 'jobs', 'nodereports', 'clusterreports', 'tasks', 'deploy',
         'schedule', 'projects', 'logs', 'items', 'sendtext', 'settings']


def _safe_url(app, name, **kw):
    # Tolerant during the incremental migration: routes not yet ported resolve to '#'.
    from starlette.routing import NoMatchFound
    try:
        return url_for(app, name, **kw)
    except NoMatchFound:
        return '#'


def build_g(app, node, ctx):
    """Per-request menu/state namespace (replaces flask.g set in update_g)."""
    amount = ctx.SCRAPYD_SERVERS_AMOUNT
    g = SimpleNamespace()
    g.IS_MOBILE = ctx.IS_MOBILE
    g.url_jobs_list = [_safe_url(app, 'jobs', node=n, ui=ctx.UI) for n in range(1, amount + 1)]
    g.multinode = ('<label title="multinode">'
                   '<svg class="icon" aria-hidden="true"><use xlink:href="#icon-servers"></use></svg>'
                   '</label>')
    if not ctx.USE_MOBILEUI:
        g.url_daemonstatus = _safe_url(app, 'api', node=node, opt='daemonstatus')
        for name in _MENU:
            setattr(g, 'url_menu_%s' % name, _safe_url(app, name, node=node))
        g.url_menu_parse = _safe_url(app, 'parse.upload', node=node)
        g.url_menu_mobileui = _safe_url(app, 'index', node=node, ui='mobile')
        any_jobs = any(job.next_run_time for job in safe_get_jobs('default'))
        g.scheduler_state_paused = scheduler.state == STATE_PAUSED and any_jobs
        g.scheduler_state_running = scheduler.state == STATE_RUNNING and any_jobs
    return g


def render(request, template_name, node, ctx, page=None, flashes=None, status_code=200):
    app = request.app
    settings = app.state.settings
    context = {}
    context.update(_version_vars())
    context.update(_static(app))
    context.update(_server_vars(settings))
    # extra processors registered on the app (e.g. tests' inject_variable)
    for cp in getattr(app.state, 'context_processors', []):
        try:
            context.update(cp(request))
        except TypeError:
            context.update(cp())
    context['node'] = node
    context['SCRAPYD_SERVER'] = ctx.SCRAPYD_SERVER
    context['g'] = build_g(app, node, ctx)
    context['url_for'] = lambda name, **kw: url_for(app, name, **kw)
    _flashes = list(flashes or [])
    context['get_flashed_messages'] = lambda with_categories=False, **kw: (
        _flashes if with_categories else [m for (_c, m) in _flashes])
    if page:
        context.update(page)
    html = env.get_template(template_name).render(**context)
    return HTMLResponse(html, status_code=status_code)
