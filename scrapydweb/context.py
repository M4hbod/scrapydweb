# coding: utf-8
"""Per-request node context (replaces the scrapyd-related parts of BaseView).

Resolves the target Scrapyd server / auth / group for a ``node`` path param and
validates the node range. Used as a FastAPI dependency: ``Depends(get_node_context)``.
"""
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


def get_node_context(request: Request, node: int = 1) -> NodeContext:
    return NodeContext(node, request.app.state.settings, request)
