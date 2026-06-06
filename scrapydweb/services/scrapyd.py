# coding: utf-8
"""Async HTTP access to Scrapyd servers (replaces BaseView.make_request).

Uses a shared ``httpx.AsyncClient``. Returns ``(status_code, json_or_text)`` with
the same shape the old sync ``make_request`` produced, including the ``-1`` /
``status='error'`` envelope on connection failure.
"""
import logging
import re

import httpx

from ..common import get_now_string

logger = logging.getLogger(__name__)

OK = 'ok'
ERROR = 'error'
NA = 'N/A'


def new_client():
    # One client per app lifespan (bound to that event loop); stored on app.state.
    return httpx.AsyncClient(follow_redirects=False, trust_env=True)


def _auth(auth):
    return tuple(auth) if auth else None


async def request_scrapyd(client, url, data=None, auth=None, as_json=True, timeout=60):
    try:
        if data is not None:
            r = await client.post(url, data=data, auth=_auth(auth), timeout=timeout)
        else:
            r = await client.get(url, auth=_auth(auth), timeout=timeout)
    except Exception as err:
        logger.error("!!!!! error with %s: %s", url, err)
        if as_json:
            return -1, dict(url=_public_url(url), status_code=-1, status=ERROR,
                            message=str(err), when=get_now_string(True))
        return -1, str(err)

    if not as_json:
        return r.status_code, r.text

    try:
        r_json = r.json()
    except ValueError as err:
        logger.error("Fail to decode json from %s: %s", url, err)
        r_json = dict(status=ERROR, message=r.text)

    message = r_json.get('message', '')
    if message and not isinstance(message, dict):
        r_json['message'] = re.sub(r'\\n', '\n', message)
    # never echo credentials back to the client (no auth tuple, no userinfo in url)
    r_json.update(dict(url=_public_url(url), status_code=r.status_code, when=get_now_string(True)))
    r_json.setdefault('status', NA)
    return r.status_code, r_json


def _public_url(url):
    return re.sub(r'//[^@/]*@', '//', url)
