# coding: utf-8
"""FastAPI dependencies shared across routers."""
from fastapi import Request

from .db import get_session  # noqa: F401  (re-exported for routers)


def get_settings(request: Request):
    return request.app.state.settings
