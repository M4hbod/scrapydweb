# coding: utf-8
"""Log / Stats / Report (ports views/files/log.py) - core async flow."""
from collections import OrderedDict, defaultdict
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from logparser import __version__ as LOGPARSER_VERSION
from logparser import parse

from ..common import get_job_without_ext, handle_slash, json_dumps
from ..context import NodeContext, get_node_context
from ..services.scrapyd import request_scrapyd
from ..urls import safe_url_for as u

router = APIRouter()
OK, ERROR, NA = 'ok', 'error', 'N/A'

REPORT_KEYS_SET = {'from_memory', 'status', 'pages', 'items', 'shutdown_reason', 'finish_reason', 'runtime',
                   'first_log_time', 'latest_log_time', 'log_categories', 'latest_matches'}
job_finished_key_dict = defaultdict(OrderedDict)
job_finished_report_dict = defaultdict(OrderedDict)


class LogHandler:
    def __init__(self, request, node, ctx, opt, project, spider, job, as_json=True):
        self.as_json = as_json  # the HTML UI is gone; JSON is the only response shape
        self.request = request
        self.app = request.app
        self.s = request.app.state.settings
        self.node = node
        self.ctx = ctx
        self.opt = opt
        self.project = project
        self.spider = spider
        self.job = job
        self.flashes = []
        self.job_key = '/%s/%s/%s/%s' % (node, project, spider, job)
        self.url = u'http://{}/logs/{}/{}/{}'.format(ctx.SCRAPYD_SERVER, project, spider, job)
        self.with_ext = request.query_params.get('with_ext', None)
        self.exts = [''] if self.with_ext else (self.s.get('SCRAPYD_LOG_EXTENSIONS', [])
                                                or ['.log', '.log.gz', '.txt', '.gz', ''])
        job_without_ext = get_job_without_ext(job) if self.with_ext else job
        self.job_without_ext = job_without_ext
        self.job_finished = request.query_params.get('job_finished', None)
        self.status_code = 0
        self.text = ''
        self.stats = {}
        self.logparser_valid = False
        self.utf8_realtime = opt == 'utf8'
        self.stats_realtime = bool(request.query_params.get('realtime')) if opt == 'stats' else False
        self.stats_logparser = opt == 'stats' and not self.stats_realtime
        self.report_logparser = opt == 'report'
        if self.utf8_realtime:
            self.flashes.append(('warning',
                                 "It's recommended to check out the latest log via: the Stats page >> View log >> Tail"))
        self.kwargs = dict(node=node, project=project, spider=spider, job=job_without_ext, url_refresh='', url_jump='')

    async def _load_db_stats(self):
        """Stats from the central collector (job_stats table). Any node, no daemons."""
        from sqlalchemy import select
        from ..db import SessionLocal
        from ..models import JobStats
        try:
            async with SessionLocal() as session:
                row = (await session.execute(select(JobStats).filter_by(
                    server=self.ctx.SCRAPYD_SERVER, project=self.project,
                    spider=self.spider, job=self.job_without_ext))).scalar_one_or_none()
        except Exception:
            return
        if row is None or not row.stats_json:
            return
        try:
            self.stats = json.loads(row.stats_json)
        except ValueError:
            return
        self.logparser_valid = True
        if row.ext is not None:
            self.exts = [row.ext]  # url_source points at the discovered extension
        self.flashes.append(('info', "Stats collected by scrapydweb at %s" % str(row.updated_at)[:19]))

    async def _request_log(self):
        for ext in self.exts:
            url = self.url + ext
            self.status_code, self.text = await request_scrapyd(self.app.state.http_client, url,
                                                                auth=self.ctx.AUTH, as_json=False)
            if self.status_code == 200:
                self.url = url
                return
        self.flashes.append(('warning', "Fail to request logfile from %s with extensions %s" % (self.url, self.exts)))
        self.url += self.exts[0]

    async def run(self):
        if self.report_logparser:
            try:
                self.stats = job_finished_report_dict[self.node][self.job_key]
                self.logparser_valid = True
                self.stats['from_memory'] = True
            except KeyError:
                pass
        if not self.logparser_valid and (self.stats_logparser or self.report_logparser):
            await self._load_db_stats()

        if not self.logparser_valid and not self.text:
            await self._request_log()
            if self.status_code != 200:
                if not self.report_logparser:
                    return JSONResponse(dict(status='error', status_code=self.status_code,
                                             url=self.url, text=self.text), status_code=200)
            else:
                self.url += self.exts[0]
        else:
            self.url += self.exts[0]

        if (not self.utf8_realtime and not self.logparser_valid and self.text and self.status_code in [0, 200]):
            self.stats = parse(self.text)
            self.stats.setdefault('crawler_engine', {})
            self.stats.setdefault('status', OK)

        if self.report_logparser:
            if self.stats and not self.stats.setdefault('from_memory', False):
                self._simplify_for_report()
                self._keep_for_report()
            return JSONResponse(self.stats or dict(status='error'),
                                status_code=200 if (self.status_code < 100 or self.stats) else self.status_code)
        self._update_kwargs()
        if self.as_json:
            finished = bool(self.job_finished or self.job_key in job_finished_key_dict[self.node])
            from ..services.job_versions import args_for_job, version_for_job
            payload = dict(status='ok', opt=self.opt, node=self.node, project=self.project,
                           spider=self.spider, job=self.job_without_ext, finished=finished,
                           version=await version_for_job(self.ctx.SCRAPYD_SERVER, self.project,
                                                         self.job_without_ext),
                           args=await args_for_job(self.ctx.SCRAPYD_SERVER, self.project,
                                                   self.job_without_ext),
                           url_source=self.kwargs.get('url_source', ''))
            if self.utf8_realtime:
                payload['text'] = self.text
                payload['last_update_timestamp'] = self.kwargs.get('last_update_timestamp')
            else:
                payload['logparser_valid'] = self.logparser_valid
                payload['stats'] = {k: v for k, v in self.kwargs.items()
                                    if k not in ('url_refresh', 'url_jump', 'url_source', 'url_opt_opposite')}
            return JSONResponse(json.loads(json_dumps(payload)))
        raise RuntimeError('unreachable: LogHandler always runs with as_json=True')

    def _simplify_for_report(self):
        for key in list(self.stats.keys()):
            if key not in REPORT_KEYS_SET:
                self.stats.pop(key)
        try:
            for key in self.stats['log_categories']:
                self.stats['log_categories'][key] = dict(count=self.stats['log_categories'][key]['count'])
        except KeyError:
            pass
        try:
            self.stats['latest_matches'] = dict(latest_item=self.stats['latest_matches']['latest_item'])
        except KeyError:
            pass

    def _keep_for_report(self):
        od = job_finished_report_dict[self.node]
        if self.job_key in od:
            return
        if (self.stats.get('shutdown_reason', NA) == NA and self.stats.get('finish_reason', NA) == NA):
            return
        if set(self.stats.keys()) == REPORT_KEYS_SET:
            od[self.job_key] = self.stats
            if len(od) > 200:
                od.popitem(last=False)

    @staticmethod
    def _ordered(adict):
        odict = OrderedDict()
        for k in ['source', 'last_update_time', 'last_update_timestamp']:
            odict[k] = adict.pop(k)
        for k in sorted(adict.keys()):
            odict[k] = adict[k]
        return odict

    def _update_kwargs(self):
        app = self.app
        if self.utf8_realtime:
            self.kwargs['text'] = self.text
            self.kwargs['last_update_timestamp'] = time.time()
            if self.job_finished or self.job_key in job_finished_key_dict[self.node]:
                self.kwargs['url_refresh'] = ''
            else:
                self.kwargs['url_refresh'] = 'javascript:location.reload(true);'
        else:
            for d in self.stats['datas']:
                d[0] = str(d[0])
            for k in ['crawler_stats', 'crawler_engine']:
                if self.stats.get(k):
                    self.stats[k] = self._ordered(self.stats[k])
            self.kwargs.update(self.stats)
            if (self.kwargs.get('finish_reason') == NA and not self.job_finished
                    and self.job_key not in job_finished_key_dict[self.node]):
                self.kwargs['url_refresh'] = 'javascript:location.reload(true);'
            if self.kwargs['url_refresh']:
                if self.stats_logparser and not self.logparser_valid:
                    self.kwargs['url_jump'] = ''
                else:
                    self.kwargs['url_jump'] = u(app, 'log', node=self.node, opt='stats', project=self.project,
                                                spider=self.spider, job=self.job, with_ext=self.with_ext,
                                                realtime='True' if self.stats_logparser else None)
        if self.with_ext and self.job.endswith('.json'):
            self.kwargs['url_source'] = ''
            self.kwargs['url_opt_opposite'] = ''
            self.kwargs['url_refresh'] = ''
            self.kwargs['url_jump'] = ''
        else:
            self.kwargs['url_source'] = self.url
            self.kwargs['url_opt_opposite'] = u(app, 'log', node=self.node,
                                                opt='utf8' if self.opt == 'stats' else 'stats',
                                                project=self.project, spider=self.spider, job=self.job,
                                                job_finished=self.job_finished, with_ext=self.with_ext)


async def log(request: Request, node: int, opt: str, project: str, spider: str, job: str,
              ctx: NodeContext = Depends(get_node_context)):
    return await LogHandler(request, node, ctx, opt, project, spider, job).run()


router.add_api_route('/{node:int}/log/{opt}/{project}/{spider}/{job}/', log,
                     methods=['GET', 'POST'], name='log')
