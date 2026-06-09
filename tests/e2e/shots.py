# coding: utf-8
"""Capture SPA screenshots for the README. Needs a running app on BASE_URL
with a configured scrapyd node + some demo jobs.

    BASE_URL=http://127.0.0.1:5000 uv run --with playwright python tests/e2e/shots.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
USER = os.environ.get('SMOKE_USER', 'admin')
PASS = os.environ.get('SMOKE_PASS', 'admin-test-pass')
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'screenshots')

SHOTS = [
    ('dashboard', '/'),
    ('jobs', '/jobs'),
    ('deploy', '/deploy'),
    ('run-spider', '/schedule'),
    ('alerts', '/alerts'),
    ('settings', '/settings'),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=2)

        me = page.request.get(BASE + '/api/auth/me').json()
        if me.get('setup_required'):
            page.request.post(BASE + '/api/auth/setup',
                              data={'username': USER, 'password': PASS},
                              headers={'Content-Type': 'application/json'})
        elif not me.get('authenticated'):
            page.request.post(BASE + '/api/auth/login',
                              data={'username': USER, 'password': PASS},
                              headers={'Content-Type': 'application/json'})

        for name, path in SHOTS:
            page.goto(BASE + path, wait_until='networkidle')
            page.wait_for_timeout(1200)
            dst = os.path.join(OUT, '%s.png' % name)
            page.screenshot(path=dst)
            print('saved', dst)
        browser.close()


if __name__ == '__main__':
    sys.exit(main())
