# coding: utf-8
"""Central job-stats collector.

Replaces the per-host logparser daemons: scrapydweb fetches every node's job
logs over HTTP, parses them with logparser's pure parse(), and stores the
result in the job_stats table. Runs as an apscheduler interval job (see
register_system_jobs) in a background thread -- everything here is sync.
"""
import gzip
import logging
import re

from logparser import parse

from ..common import json_dumps, session
from ..db_sync import SyncSessionLocal
from ..models import JobStats

logger = logging.getLogger(__name__)

MAX_LOG_BYTES = 20 * 1024 * 1024  # logs larger than this are skipped (size recorded)
DEFAULT_EXTENSIONS = ['.log', '.log.gz', '.txt', '.gz', '']
CONTENT_RANGE_PATTERN = re.compile(r'bytes \d+-\d+/(\d+)')


def _decode(content):
    if content[:2] == b'\x1f\x8b':  # gzip magic (proxy may strip Content-Encoding)
        try:
            content = gzip.decompress(content)
        except OSError:
            pass
    return content.decode('utf-8', errors='ignore')


def _probe(url, auth):
    """Return (size, full_body_or_None). Cheap Range probe; tolerate naive servers."""
    try:
        r = session.get(url, auth=auth, headers={'Range': 'bytes=0-0'}, timeout=30)
    except Exception:
        return None, None
    if r.status_code == 206:
        m = CONTENT_RANGE_PATTERN.search(r.headers.get('Content-Range', ''))
        return (int(m.group(1)) if m else None), None
    if r.status_code == 200:  # server ignored Range: body IS the full log, reuse it
        return len(r.content), r.content
    return None, None


def _fetch(url, auth):
    try:
        r = session.get(url, auth=auth, timeout=60)
    except Exception:
        return None
    return r.content if r.status_code == 200 else None


def _collect_server(s, server, auth, extensions, settings=None, node=1, alert_rules=None):
    url_jobs = 'http://%s/jobs' % server
    r = session.get(url_jobs, auth=auth, timeout=30)
    if r.status_code != 200 or '<h1>Jobs</h1>' not in r.text:
        logger.debug('stats_collector: %s returned %s', url_jobs, r.status_code)
        return 0

    from ..routers.jobs import _parse  # lazy: routers/__init__ has side effects
    jobs = [j for j in _parse(r.text) if j['start']]

    rows = {(row.project, row.spider, row.job): row
            for row in s.query(JobStats).filter_by(server=server).all()}

    parsed = 0
    for job in jobs:
        key = (job['project'], job['spider'], job['job'])
        row = rows.get(key)
        running = not job['finish']
        base = 'http://{}/logs/{}/{}/{}'.format(server, *key)

        # discover the log extension once per job
        ext = row.ext if (row and row.ext is not None) else None
        size = body = None
        if ext is not None:
            size, body = _probe(base + ext, auth)
        if size is None:
            for cand in extensions:
                size, body = _probe(base + cand, auth)
                if size is not None:
                    ext = cand
                    break
        if size is None:
            continue  # log not reachable (rotated away?)

        finished_parsed = row is not None and row.finish_reason not in (None, '', 'N/A')
        if row is not None and row.size == size and (finished_parsed or not running):
            continue  # nothing new

        if row is None:
            row = JobStats(server=server, project=key[0], spider=key[1], job=key[2])
            s.add(row)
            rows[key] = row
        row.ext = ext
        row.size = size

        if size > MAX_LOG_BYTES:
            logger.warning('stats_collector: %s%s is %s bytes (> %s), skipping parse',
                           base, ext, size, MAX_LOG_BYTES)
            continue

        if body is None:
            body = _fetch(base + ext, auth)
            if body is None:
                continue
        stats = parse(_decode(body))
        pages, items = stats.get('pages'), stats.get('items')
        row.pages = pages if isinstance(pages, int) else None
        row.items = items if isinstance(items, int) else None
        row.runtime = str(stats.get('runtime') or '')[:20] or None
        row.finish_reason = str(stats.get('finish_reason') or 'N/A')[:64]
        row.first_log_time = str(stats.get('first_log_time') or '')[:19] or None
        row.latest_log_time = str(stats.get('latest_log_time') or '')[:19] or None
        row.stats_json = json_dumps(stats, sort_keys=False, indent=None)
        parsed += 1
        if settings is not None:
            try:
                from .alert_rules import effective_settings
                from .alerts import evaluate_alerts
                eff = effective_settings(settings, alert_rules or [], key[0], key[1])
                evaluate_alerts(eff, server, node, auth, row, stats, running)
            except Exception as err:
                logger.warning('alert evaluation failed for %s: %s', key, err)
    return parsed


def collect_all(config):
    """Collect stats for every configured scrapyd server. apscheduler entrypoint."""
    servers = config.get('SCRAPYD_SERVERS', []) or []
    auths = config.get('SCRAPYD_SERVERS_AUTHS', []) or [None] * len(servers)
    extensions = config.get('SCRAPYD_LOG_EXTENSIONS', []) or DEFAULT_EXTENSIONS
    from .alert_rules import load_rules_sync
    alert_rules = load_rules_sync()  # once per cycle, shared by every server

    total = 0
    for idx, server in enumerate(servers):
        auth = auths[idx] if idx < len(auths) else None
        s = SyncSessionLocal()
        try:
            total += _collect_server(s, server, auth, extensions,
                                     settings=config, node=idx + 1,
                                     alert_rules=alert_rules)
            s.commit()
        except Exception as err:
            s.rollback()
            logger.warning('stats_collector: %s failed: %s', server, err)
        finally:
            s.close()
    if total:
        logger.info('stats_collector: parsed %s job log(s)', total)
    return total
