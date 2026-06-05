# coding: utf-8
"""Framework-agnostic helpers (no web framework imports).

Flask-specific helpers that lived here (authenticate, get_response_from_view,
the requests Session, handle_metadata) are reimplemented in the async
services/deps during the FastAPI migration.
"""
import json
import os
import time


def find_scrapydweb_settings_py(filename, path, prevpath=None):
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, filename)
    if os.path.exists(cfgfile):
        return cfgfile


def get_now_string(allow_space=False):
    if allow_space:
        return time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return time.strftime('%Y-%m-%dT%H_%M_%S')


def handle_slash(string):
    if not string:
        return string
    return string.replace('\\', '/')


def json_dumps(obj, sort_keys=True, indent=4, ensure_ascii=False):
    return json.dumps(obj, sort_keys=sort_keys, indent=indent, ensure_ascii=ensure_ascii)
