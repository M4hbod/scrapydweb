# coding: utf-8
"""Prometheus /metrics endpoint (token-protected by the session_auth middleware).

Scrape it with an API token, e.g. Prometheus scrape_config:
    bearer_token: sdw_xxxxxxxx
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..services.metrics import render_prometheus

router = APIRouter()

_CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'


@router.get('/metrics', name='metrics')
async def metrics(request: Request):
    if not request.app.state.settings.get('ENABLE_METRICS', True):
        return JSONResponse({'status': 'error', 'message': 'metrics disabled'}, status_code=404)
    try:
        text = await render_prometheus(request.app)
    except Exception as err:  # never break the scrape with a 500 stacktrace
        return PlainTextResponse('# metrics error: %s\nscrapydweb_up 0\n' % err,
                                 media_type=_CONTENT_TYPE)
    return PlainTextResponse(text, media_type=_CONTENT_TYPE)
