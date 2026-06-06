# coding: utf-8
"""Per-request node context (replaces the scrapyd-related parts of BaseView).

Resolves the target Scrapyd server / auth / group for a ``node`` path param and
validates the node range. Used as a FastAPI dependency: ``Depends(get_node_context)``.
"""
import re

from fastapi import Request

DEFAULT_LATEST_VERSION = 'default: the latest version'


class NodeIndexError(Exception):
    def __init__(self, node, amount):
        self.node = node
        self.amount = amount
        if amount == 0:
            msg = 'no scrapyd servers configured -- add one on the Settings page'
        else:
            msg = 'node index error: %s, which should be between 1 and %s' % (node, amount)
        super().__init__(msg)


class NodeContext:
    def __init__(self, node, settings, request=None):
        servers = settings.get('SCRAPYD_SERVERS') or []
        self.SCRAPYD_SERVERS = servers
        self.SCRAPYD_SERVERS_AMOUNT = len(servers)
        if not (0 < node <= self.SCRAPYD_SERVERS_AMOUNT):
            raise NodeIndexError(node, self.SCRAPYD_SERVERS_AMOUNT)

        self.node = node
        self.SCRAPYD_SERVER = servers[node - 1]
        groups = settings.get('SCRAPYD_SERVERS_GROUPS') or ['']
        auths = settings.get('SCRAPYD_SERVERS_AUTHS') or [None]
        self.GROUP = groups[node - 1]
        self.AUTH = auths[node - 1]

        ua = request.headers.get('user-agent', '') if request is not None else ''
        self.IS_MOBILE = bool(re.search(
            r'Android|webOS|iPad|iPhone|iPod|BlackBerry|IEMobile|Opera Mini', ua, re.I))
        self.IS_IPAD = bool(re.search(r'iPad', ua, re.I))
        self.IS_IE_EDGE = bool(re.search(r'MSIE|Edge', ua, re.I))
        # Mobile-UI feature removed -- one responsive UI is served to every device.
        self.USE_MOBILEUI = False
        self.UI = None
        self.POST = request is not None and request.method == 'POST'

    def selected_nodes_from_form(self, form):
        return [n for n in range(1, self.SCRAPYD_SERVERS_AMOUNT + 1) if form.get(str(n)) == 'on']


def compute_features(settings, ctx, jobs_style, any_jobs, scheduler_state):
    from .scheduler import STATE_PAUSED
    from .vars import DEMO_PROJECTS_PATH, SQLALCHEMY_DATABASE_URI
    g = settings.get
    F = ''
    F += 'D' if jobs_style == 'database' else 'C'
    F += 'd' if (g('SCRAPY_PROJECTS_DIR', '') or DEMO_PROJECTS_PATH) != DEMO_PROJECTS_PATH else '-'
    F += 'Sl' if g('ENABLE_SLACK_ALERT', False) else '-'
    F += 'Tg' if g('ENABLE_TELEGRAM_ALERT', False) else '-'
    F += 'Em' if g('ENABLE_EMAIL_ALERT', False) else '-'
    F += 'P' if ctx.IS_MOBILE else '-'
    F += 'M' if ctx.USE_MOBILEUI else '-'
    F += 'S' if g('ENABLE_HTTPS', False) else '-'
    if scheduler_state == STATE_PAUSED:
        F += '-'
    elif any_jobs:
        F += 'T'
    else:
        F += 't'
    if not SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        F += SQLALCHEMY_DATABASE_URI[:3]
    return F


def get_node_context(request: Request, node: int = 1) -> NodeContext:
    return NodeContext(node, request.app.state.settings, request)
