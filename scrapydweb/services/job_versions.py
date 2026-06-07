# coding: utf-8
"""Record which project version each scrapyd job was scheduled with.

Scrapyd's listjobs.json does not return the version, so it is captured at
schedule time (the only moment it is knowable) into the job_version table and
surfaced on job rows / the log page to link the code viewer.

Async helpers serve the request handlers; the *_sync twins serve the
APScheduler thread (timer tasks), which has no event loop.
"""
import logging

from sqlalchemy import select

from ..context import DEFAULT_LATEST_VERSION
from ..models import JobVersion

logger = logging.getLogger(__name__)


def _explicit(version):
    return version if version and version != DEFAULT_LATEST_VERSION else None


async def resolve_version(client, server, auth, project, explicit):
    """The version a schedule call will run: explicit, else scrapyd's latest, else None."""
    if _explicit(explicit):
        return explicit
    from .scrapyd import request_scrapyd
    try:
        _code, js = await request_scrapyd(
            client, 'http://%s/listversions.json?project=%s' % (server, project),
            auth=auth, as_json=True)
        versions = js.get('versions') or []
        return versions[-1] if versions else None
    except Exception as err:
        logger.debug('Fail to resolve latest version of %s on %s: %s', project, server, err)
        return None


def resolve_version_sync(server, auth, project, explicit):
    if _explicit(explicit):
        return explicit
    from ..common import session
    try:
        r = session.get('http://%s/listversions.json?project=%s' % (server, project),
                        auth=tuple(auth) if auth else None, timeout=30)
        versions = r.json().get('versions') or []
        return versions[-1] if versions else None
    except Exception as err:
        logger.debug('Fail to resolve latest version of %s on %s: %s', project, server, err)
        return None


def _upsert(session, server, project, spider, job, version, source):
    row = session.execute(select(JobVersion).filter_by(
        server=server, project=project, job=job)).scalar_one_or_none()
    if row is None:
        session.add(JobVersion(server=server, project=project, spider=spider,
                               job=job, version=version, source=source))
    else:
        row.spider, row.version, row.source = spider, version, source


async def record_job_version(server, project, spider, job, version, source='run'):
    """Upsert (server, project, job) -> version; never raises (audit data only)."""
    if not (version and job):
        return
    from ..db import SessionLocal, create_all_for_bind
    try:
        await create_all_for_bind('jobs')
        async with SessionLocal() as s:
            await s.run_sync(_upsert, server, project, spider, job, version, source)
            await s.commit()
    except Exception as err:
        logger.warning('Fail to record job version %s/%s=%s: %s', project, job, version, err)


def record_job_version_sync(server, project, spider, job, version, source='task'):
    if not (version and job):
        return
    from ..db_sync import SyncSessionLocal
    try:
        with SyncSessionLocal() as s:
            _upsert(s, server, project, spider, job, version, source)
            s.commit()
    except Exception as err:
        logger.warning('Fail to record job version %s/%s=%s: %s', project, job, version, err)


async def versions_for_server(server):
    """{(project, job): version} for one scrapyd server."""
    from ..db import SessionLocal
    try:
        async with SessionLocal() as s:
            rows = (await s.execute(select(JobVersion).filter_by(server=server))).scalars().all()
        return {(r.project, r.job): r.version for r in rows}
    except Exception:
        return {}


async def version_for_job(server, project, job):
    from ..db import SessionLocal
    try:
        async with SessionLocal() as s:
            row = (await s.execute(select(JobVersion).filter_by(
                server=server, project=project, job=job))).scalar_one_or_none()
        return row.version if row else None
    except Exception:
        return None
