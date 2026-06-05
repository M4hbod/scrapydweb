# coding: utf-8
"""A redirect that carries the target URL in the body (like Flask's redirect).

Some tests/JS read the flash message out of the redirect body, not just the
Location header, so an empty-body Starlette RedirectResponse is not enough.
"""
from starlette.responses import Response


def redirect(url, status_code=302):
    body = ('<!DOCTYPE HTML><html><head><title>Redirecting...</title></head>'
            '<body><p>You should be redirected automatically to target URL: '
            '<a href="%s">%s</a></p></body></html>') % (url, url)
    return Response(content=body, status_code=status_code,
                    headers={'Location': url}, media_type='text/html')
