# coding: utf-8
"""services/job_versions.py: resolve + record, async and sync twins."""
import asyncio
import time

import httpx
import pytest

from scrapydweb.services import job_versions
from tests.utils import cst

PROJECT = cst.PROJECT
AUTH = ('admin', '12345')


@pytest.fixture
def seeded(fake_scrapyd):
    fake_scrapyd.state.projects.setdefault(PROJECT, {})
    fake_scrapyd.state.projects[PROJECT]['v-old'] = b'a'
    fake_scrapyd.state.projects[PROJECT]['v-new'] = b'b'
    fake_scrapyd.state.spiders.setdefault(PROJECT, ['test'])
    return fake_scrapyd


def _run(coro):
    return asyncio.run(coro)


def test_resolve_explicit_short_circuits(seeded):
    before = seeded.state.counters['requests'].get('listversions', 0)
    v = _run(job_versions.resolve_version(None, seeded.address, AUTH, PROJECT, 'pinned'))
    assert v == 'pinned'
    assert seeded.state.counters['requests'].get('listversions', 0) == before  # no HTTP


def test_resolve_latest_async(seeded):
    async def go():
        async with httpx.AsyncClient() as client:
            return await job_versions.resolve_version(
                client, seeded.address, AUTH, PROJECT, cst.DEFAULT_LATEST_VERSION)
    assert _run(go()) == 'v-new'


def test_resolve_latest_sync(seeded):
    v = job_versions.resolve_version_sync(seeded.address, AUTH, PROJECT, None)
    assert v == 'v-new'


def test_resolve_failure_returns_none():
    v = job_versions.resolve_version_sync('scrapydweb-fake-domain.com:443', None, PROJECT, None)
    assert v is None


def _sync_lookup(server, project, job):
    from sqlalchemy import select
    from scrapydweb.db_sync import SyncSessionLocal
    from scrapydweb.models import JobVersion
    with SyncSessionLocal() as s:
        row = s.execute(select(JobVersion).filter_by(
            server=server, project=project, job=job)).scalar_one_or_none()
        return row.version if row else None


def test_record_upsert_and_lookup_sync(client):
    # the global async engine is bound to the TestClient's loop -- exercise the
    # sync twins directly (the async path is covered by the schedule tests)
    server = 'unit-test-server:6800'
    job = 'jv-%s' % int(time.time())
    job_versions.record_job_version_sync(server, PROJECT, 'test', job, 'v1')
    job_versions.record_job_version_sync(server, PROJECT, 'test', job, 'v2')  # upsert
    assert _sync_lookup(server, PROJECT, job) == 'v2'


def test_record_noop_without_version(client):
    server = 'unit-test-server:6800'
    job_versions.record_job_version_sync(server, PROJECT, 'test', 'jv-none', None)
    assert _sync_lookup(server, PROJECT, 'jv-none') is None
