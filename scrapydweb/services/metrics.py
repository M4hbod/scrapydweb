# coding: utf-8
"""Prometheus exposition for scrapydweb.

Rendered on each scrape from the data scrapydweb already keeps: the persistent
JobStats table (per-job parsed pages/items/finish_reason/runtime, never pruned),
the per-node Job tables (running/pending), and a live daemonstatus probe. No new
storage. Labels are kept to {project,spider} (+ {node,server} for node health)
so cardinality stays bounded -- no per-job series.

The metric set is chosen so Grafana can alert on the real failure modes:
  - parser broke / zero items   -> scrapydweb_spider_last_run_items == 0
  - spider idle / schedule dead  -> time() - scrapydweb_spider_last_finish_timestamp_seconds > N
  - failing spider              -> rate(scrapydweb_jobs_finished_total{outcome="failed"}[..]) ratio
  - hung job                    -> scrapydweb_spider_running_max_runtime_seconds > N
  - backlog                     -> scrapydweb_jobs_pending
  - node down                   -> scrapydweb_scrapyd_node_up == 0
  - throughput drop             -> rate(scrapydweb_items_scraped_total[..])
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from ..db import SessionLocal, get_jobs_table
from ..models import JobStats

logger = logging.getLogger(__name__)

_NS = 'scrapydweb_'


def _esc(v):
    return str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


def _labels(d):
    return ','.join('%s="%s"' % (k, _esc(v)) for k, v in d.items())


def _runtime_secs(s):
    """'0:01:30' / '1:02:03.45' -> seconds (float); None on parse failure."""
    if not s:
        return None
    try:
        parts = str(s).split(':')
        if len(parts) != 3:
            return None
        h, m, sec = parts
        return int(h) * 3600 + int(m) * 60 + float(sec)
    except (ValueError, TypeError):
        return None


def _ts(s):
    """'%Y-%m-%d %H:%M:%S' -> unix seconds; None on failure."""
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S').timestamp()
    except (ValueError, TypeError):
        return None


def _finished(reason):
    return reason not in (None, '', 'N/A')


# A run counts as failed ONLY for genuine error/abort reasons. Anything else that
# reached a finish_reason is a success — including 'finished' AND controlled stops
# (CLOSESPIDER_PAGECOUNT/ITEMCOUNT/TIMEOUT, or a custom CloseSpider("...") raised on
# purpose). Classifying ok as `== 'finished'` wrongly flags every deliberate early
# stop as a failure.
_FAILED_REASONS = frozenset({
    'cancelled', 'shutdown', 'closespider_errorcount', 'memusage_exceeded',
    'error',  # streamwide spiders raise CloseSpider("error") on genuine failures
})


def _ok(reason):
    return reason not in _FAILED_REASONS


class _Agg:
    __slots__ = ('items', 'pages', 'ok', 'failed', 'last_ts', 'last_items',
                 'last_pages', 'last_ok', 'running', 'pending', 'run_max_rt')

    def __init__(self):
        self.items = self.pages = 0
        self.ok = self.failed = 0
        self.last_ts = None
        self.last_items = self.last_pages = 0
        self.last_ok = 0
        self.running = self.pending = 0
        self.run_max_rt = 0.0


async def _node_up(client, server, auth):
    from .scrapyd import request_scrapyd
    try:
        code, js = await request_scrapyd(
            client, 'http://%s/daemonstatus.json' % server, auth=auth, as_json=True, timeout=3)
        return 1 if code == 200 and js.get('status') == 'ok' else 0
    except Exception:
        return 0


async def render_prometheus(app):
    settings = app.state.settings
    servers = settings.get('SCRAPYD_SERVERS', []) or []
    auths = settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None] * len(servers)
    client = app.state.http_client

    agg = {}  # (project, spider) -> _Agg
    node_up = {}  # node -> (server, up)

    # node health in parallel
    up_results = await asyncio.gather(
        *[_node_up(client, s, auths[i] if i < len(auths) else None) for i, s in enumerate(servers)])
    for i, s in enumerate(servers):
        node_up[i + 1] = (s, up_results[i])

    async with SessionLocal() as session:
        # JobStats: cumulative items/pages, finished outcomes, last-run per spider
        for server in servers:
            rows = (await session.execute(
                select(JobStats).filter_by(server=server))).scalars().all()
            for r in rows:
                if not _finished(r.finish_reason):
                    continue
                a = agg.setdefault((r.project, r.spider), _Agg())
                items = int(r.items or 0)
                pages = int(r.pages or 0)
                a.items += items
                a.pages += pages
                ok = _ok(r.finish_reason)
                if ok:
                    a.ok += 1
                else:
                    a.failed += 1
                ts = _ts(r.latest_log_time)
                if ts is not None and (a.last_ts is None or ts > a.last_ts):
                    a.last_ts = ts
                    a.last_items = items
                    a.last_pages = pages
                    a.last_ok = 1 if ok else 0

        # Job tables: current running/pending + running runtimes
        for node, (server, _up) in node_up.items():
            try:
                Job = await get_jobs_table(node, server)
                jobs = (await session.execute(
                    select(Job).filter(Job.deleted == '0',
                                       Job.status.in_(('0', '1'))))).scalars().all()
                for j in jobs:
                    a = agg.setdefault((j.project, j.spider), _Agg())
                    if j.status == '1':
                        a.running += 1
                        rt = _runtime_secs(j.runtime)
                        if rt and rt > a.run_max_rt:
                            a.run_max_rt = rt
                    elif j.status == '0':
                        a.pending += 1
            except Exception as err:
                logger.warning('metrics: jobs table for node %s failed: %s', node, err)

    # ---- render ----
    out = []

    def block(name, mtype, help_, samples):
        out.append('# HELP %s%s %s' % (_NS, name, help_))
        out.append('# TYPE %s%s %s' % (_NS, name, mtype))
        for labels, value in samples:
            lbl = '{%s}' % _labels(labels) if labels else ''
            out.append('%s%s%s %s' % (_NS, name, lbl, value))

    block('up', 'gauge', 'scrapydweb is serving metrics.', [({}, 1)])
    block('scrapyd_node_up', 'gauge', 'Scrapyd node reachable (daemonstatus).',
          [({'node': n, 'server': s}, up) for n, (s, up) in sorted(node_up.items())])

    def samples(fn):
        return [(dict(project=p, spider=sp), fn(a)) for (p, sp), a in sorted(agg.items())]

    block('items_scraped_total', 'counter', 'Cumulative items across finished jobs.',
          samples(lambda a: a.items))
    block('pages_crawled_total', 'counter', 'Cumulative pages across finished jobs.',
          samples(lambda a: a.pages))
    # finished by outcome (two series per spider)
    out.append('# HELP %sjobs_finished_total Finished jobs by outcome.' % _NS)
    out.append('# TYPE %sjobs_finished_total counter' % _NS)
    for (p, sp), a in sorted(agg.items()):
        out.append('%sjobs_finished_total{project="%s",spider="%s",outcome="ok"} %s'
                   % (_NS, _esc(p), _esc(sp), a.ok))
        out.append('%sjobs_finished_total{project="%s",spider="%s",outcome="failed"} %s'
                   % (_NS, _esc(p), _esc(sp), a.failed))
    block('jobs_running', 'gauge', 'Currently running jobs.', samples(lambda a: a.running))
    block('jobs_pending', 'gauge', 'Currently pending jobs.', samples(lambda a: a.pending))
    block('spider_running_max_runtime_seconds', 'gauge',
          'Runtime of the longest currently-running job.', samples(lambda a: a.run_max_rt))
    block('spider_last_run_items', 'gauge', 'Items of the most recent finished run.',
          samples(lambda a: a.last_items))
    block('spider_last_run_pages', 'gauge', 'Pages of the most recent finished run.',
          samples(lambda a: a.last_pages))
    block('spider_last_run_ok', 'gauge', '1 if the most recent finished run succeeded.',
          samples(lambda a: a.last_ok))
    block('spider_last_finish_timestamp_seconds', 'gauge',
          'Unix time of the most recent finished run.',
          [(dict(project=p, spider=sp), int(a.last_ts))
           for (p, sp), a in sorted(agg.items()) if a.last_ts is not None])

    return '\n'.join(out) + '\n'
