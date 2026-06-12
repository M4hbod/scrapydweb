# coding: utf-8
"""Cluster-overview dashboard aggregates for the Servers page.

All figures come from the local **jobs** database (the per-server Job tables that
the Jobs page / servers XHR populate) -- never a live Scrapyd fan-out -- so the
widgets render fast and cannot hang on an unreachable node. Everything here is
best-effort: any failure for one node degrades to zeros for that node, never an
exception that would break the page.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from ..db import SessionLocal, get_jobs_table
from ..models import JobStats
from ..urls import safe_url_for

# Job.status codes (mirror routers/jobs.py)
_PENDING, _RUNNING, _FINISHED = '0', '1', '2'
_PILL = {
    _PENDING:  ('PENDING', 'pend'),
    _RUNNING:  ('RUNNING', 'run'),
    _FINISHED: ('FINISHED', 'fin'),
}
_THROUGHPUT_DAYS = 14
_ACTIVITY_LIMIT = 12


def _ago(dt):
    """Compact relative time, e.g. '12s', '4m', '3h', '2d'. '' if unknown."""
    if not dt:
        return ''
    try:
        secs = (datetime.now() - dt).total_seconds()
    except TypeError:
        return ''
    if secs < 0:
        secs = 0
    if secs < 60:
        return '%ds' % int(secs)
    if secs < 3600:
        return '%dm' % int(secs // 60)
    if secs < 86400:
        return '%dh' % int(secs // 3600)
    return '%dd' % int(secs // 86400)


async def build_cluster_dashboard(app, ctx=None):
    """Return a dict the servers template renders, or None on total failure."""
    settings = app.state.settings
    servers = settings.get('SCRAPYD_SERVERS', []) or []
    groups = settings.get('SCRAPYD_SERVERS_GROUPS', []) or []
    amount = len(servers)

    kpi = dict(running=0, pending=0, finished=0, pages=0, items=0)
    nodes = []
    activity_pool = []          # (update_time, event_dict)
    finish_times = []           # datetimes of finished jobs (throughput)

    try:
        async with SessionLocal() as session:
            for idx in range(amount):
                node = idx + 1
                server = servers[idx]
                group = groups[idx] if idx < len(groups) else ''
                summary = dict(index=node, server=server, group=group,
                               running=0, pending=0, finished=0,
                               jobs_total=0, pages=0, items=0, last='')
                try:
                    Job = await get_jobs_table(node, server)

                    # per-status job counts
                    rows = (await session.execute(
                        select(Job.status, func.count(Job.id))
                        .where(Job.deleted == '0')
                        .group_by(Job.status))).all()
                    for status, cnt in rows:
                        cnt = int(cnt or 0)
                        summary['jobs_total'] += cnt
                        if status == _RUNNING:
                            summary['running'] = cnt
                        elif status == _PENDING:
                            summary['pending'] = cnt
                        elif status == _FINISHED:
                            summary['finished'] = cnt

                    # pages/items come from the parsed log stats (JobStats), which the
                    # Job table doesn't reliably carry; key them for the activity feed too
                    st_rows = (await session.execute(
                        select(JobStats.project, JobStats.spider, JobStats.job,
                               JobStats.pages, JobStats.items)
                        .filter_by(server=server))).all()
                    st_map = {}
                    for p, sp, jb, pg, it in st_rows:
                        st_map[(p, sp, jb)] = (pg, it)
                        summary['pages'] += int(pg or 0)
                        summary['items'] += int(it or 0)

                    # most-recent jobs for the activity feed
                    recent = (await session.execute(
                        select(Job).where(Job.deleted == '0')
                        .order_by(Job.update_time.desc()).limit(_ACTIVITY_LIMIT))).scalars().all()
                    last_dt = None
                    for j in recent:
                        last_dt = last_dt or j.update_time
                        label, cls = _PILL.get(j.status, ('', 'fin'))
                        pg, it = st_map.get((j.project, j.spider, j.job), (j.pages, j.items))
                        activity_pool.append((j.update_time or datetime.min, dict(
                            node=node, server=server, project=j.project, spider=j.spider,
                            job=j.job, status_label=label, status_class=cls,
                            pages=pg, items=it, runtime=j.runtime,
                            when=_ago(j.update_time))))
                    summary['last'] = _ago(last_dt)

                    # finished timestamps for the throughput chart
                    fts = (await session.execute(
                        select(Job.finish).where(
                            Job.status == _FINISHED, Job.deleted == '0',
                            Job.finish.isnot(None)))).scalars().all()
                    finish_times.extend(t for t in fts if t)
                except Exception:
                    pass  # node degrades to zeros; never break the page

                kpi['running'] += summary['running']
                kpi['pending'] += summary['pending']
                kpi['finished'] += summary['finished']
                kpi['pages'] += summary['pages']
                kpi['items'] += summary['items']
                nodes.append(summary)
    except Exception:
        return None

    # relative load bar: each node's running vs the busiest node
    max_running = max([n['running'] for n in nodes], default=0)
    for n in nodes:
        n['load_pct'] = int(round(n['running'] / max_running * 100)) if max_running else 0

    # activity feed: newest first, capped
    activity_pool.sort(key=lambda t: t[0], reverse=True)
    activity = [e for _dt, e in activity_pool[:_ACTIVITY_LIMIT]]

    # throughput: finished jobs per day for the last N days
    today = datetime.now().date()
    buckets = {today - timedelta(days=i): 0 for i in range(_THROUGHPUT_DAYS)}
    for t in finish_times:
        d = t.date()
        if d in buckets:
            buckets[d] += 1
    ordered = sorted(buckets.items())  # oldest -> newest
    tmax = max([c for _d, c in ordered], default=0)
    throughput = [dict(label=d.strftime('%m-%d'), count=c,
                       pct=int(round(c / tmax * 100)) if tmax else 0)
                  for d, c in ordered]

    return dict(
        nodes_total=amount,
        nodes_online=sum(1 for n in nodes if n['jobs_total'] or n['running'] or n['pending']),
        kpi=kpi,
        nodes=nodes,
        activity=activity,
        throughput=throughput,
        throughput_total=sum(c['count'] for c in throughput),
    )


async def search_jobs(app, q, limit=20):
    """Search the local jobs DB across nodes for project/spider/job matching q.

    Returns a list of {node, server, project, spider, job, status_label,
    status_class, url} where url opens that job's stats page. Best-effort.
    """
    q = (q or '').strip()
    if not q:
        return []
    settings = app.state.settings
    servers = settings.get('SCRAPYD_SERVERS', []) or []
    like = '%%%s%%' % q
    out = []
    try:
        async with SessionLocal() as session:
            for idx in range(len(servers)):
                node = idx + 1
                server = servers[idx]
                try:
                    Job = await get_jobs_table(node, server)
                    rows = (await session.execute(
                        select(Job).where(
                            Job.deleted == '0',
                            or_(Job.project.ilike(like), Job.spider.ilike(like), Job.job.ilike(like)))
                        .order_by(Job.update_time.desc()).limit(limit))).scalars().all()
                    for j in rows:
                        label, cls = _PILL.get(j.status, ('', 'fin'))
                        out.append(dict(
                            node=node, server=server, project=j.project, spider=j.spider,
                            job=j.job, status_label=label, status_class=cls,
                            url=safe_url_for(app, 'log', node=node, opt='stats',
                                             project=j.project, spider=j.spider, job=j.job)))
                except Exception:
                    pass
    except Exception:
        return []
    return out[:limit]
