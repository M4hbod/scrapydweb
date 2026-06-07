# coding: utf-8
"""Playwright smoke test for the SPA.

Run via `just e2e` (starts a server, runs this, stops it) or standalone:
    BASE_URL=http://127.0.0.1:5000 uv run --with playwright python tests/e2e/smoke.py
Requires playwright browsers (`uv run --with playwright playwright install chromium`).
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
PAGES = ['/', '/jobs', '/tasks', '/schedule', '/deploy', '/projects',
         '/settings']
VIEWPORTS = [(1440, 900), (768, 1024), (390, 844)]

failures = []

USER = os.environ.get('SMOKE_USER', 'admin')
PASS = os.environ.get('SMOKE_PASS', 'smoke-pass-123')

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)

    # authenticate (first run -> create-admin setup screen; otherwise login)
    me = page.request.get(BASE + '/api/auth/me').json()
    if me.get('setup_required'):
        r = page.request.post(BASE + '/api/auth/setup',
                              data={'username': USER, 'password': PASS},
                              headers={'Content-Type': 'application/json'})
    elif not me.get('authenticated'):
        r = page.request.post(BASE + '/api/auth/login',
                              data={'username': USER, 'password': PASS},
                              headers={'Content-Type': 'application/json'})
    me = page.request.get(BASE + '/api/auth/me').json()
    if not me.get('authenticated'):
        sys.exit('E2E FAIL: could not authenticate (%s)' % me)

    for path in PAGES:
        page.goto(BASE + path, wait_until='networkidle')
        page.wait_for_timeout(400)
        if not page.locator('#root > *').count():
            failures.append('%s: SPA did not render' % path)

    for w, h in VIEWPORTS:
        page.set_viewport_size({'width': w, 'height': h})
        page.goto(BASE + '/', wait_until='networkidle')
        page.wait_for_timeout(400)
        overflow = page.evaluate(
            'document.documentElement.scrollWidth - document.documentElement.clientWidth')
        if overflow > 0:
            failures.append('viewport %sx%s: %spx horizontal overflow' % (w, h, overflow))

    # global search opens
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.goto(BASE + '/', wait_until='networkidle')
    page.keyboard.press('Control+k')
    page.wait_for_timeout(300)
    if not page.locator('[data-slot="command-input"]').count():
        failures.append('search dialog did not open on Ctrl+K')

    if errors:
        failures.append('console/page errors: %s' % errors[:5])
    browser.close()

if failures:
    print('E2E FAIL')
    for f in failures:
        print(' -', f)
    sys.exit(1)
print('E2E OK: %d pages, %d viewports, search dialog, no console errors'
      % (len(PAGES), len(VIEWPORTS)))
