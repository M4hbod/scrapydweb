# coding: utf-8
"""Index redirect (ports views/index.py)."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ..context import NodeContext, get_node_context
from ..urls import url_for

router = APIRouter()


async def index(request: Request, node: int = 1, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    mobile = ctx.IS_MOBILE and not ctx.IS_IPAD
    if ctx.SCRAPYD_SERVERS_AMOUNT == 1:
        target = url_for(app, 'jobs', node=node, ui=('mobile' if mobile else ctx.UI))
    elif ctx.USE_MOBILEUI or mobile:
        target = url_for(app, 'jobs', node=node, ui='mobile')
    else:
        target = url_for(app, 'servers', node=node, ui=ctx.UI)
    return RedirectResponse(target, status_code=302)


router.add_api_route('/{node:int}/', index, methods=['GET'], name='index')
router.add_api_route('/', index, methods=['GET'], name='index')
