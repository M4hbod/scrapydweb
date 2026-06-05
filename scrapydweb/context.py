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
        super().__init__('node index error: %s, which should be between 1 and %s' % (node, amount))


class NodeContext:
    def __init__(self, node, settings, request=None):
        servers = settings.get('SCRAPYD_SERVERS') or ['127.0.0.1:6800']
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
        self.LOCAL_SCRAPYD_SERVER = settings.get('LOCAL_SCRAPYD_SERVER', '')
        self.IS_LOCAL_SCRAPYD_SERVER = self.SCRAPYD_SERVER == self.LOCAL_SCRAPYD_SERVER

        ua = request.headers.get('user-agent', '') if request is not None else ''
        self.IS_MOBILE = bool(re.search(
            r'Android|webOS|iPad|iPhone|iPod|BlackBerry|IEMobile|Opera Mini', ua, re.I))
        self.IS_IPAD = bool(re.search(r'iPad', ua, re.I))
        self.USE_MOBILEUI = (request is not None
                             and request.query_params.get('ui', '') == 'mobile')
        self.UI = 'mobile' if self.USE_MOBILEUI else None


def get_node_context(node: int, request: Request) -> NodeContext:
    return NodeContext(node, request.app.state.settings, request)
