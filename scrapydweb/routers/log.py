# coding: utf-8
"""Log / Stats / Report (ports views/files/log.py) - core async flow."""
from collections import OrderedDict, defaultdict
import io
import json
import os
import re
import tarfile
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from logparser import __version__ as LOGPARSER_VERSION
from logparser import parse

from ..common import get_job_without_ext, handle_slash, json_dumps
from ..context import NodeContext, get_node_context
from ..services.scrapyd import request_scrapyd
from ..templating import render
from ..urls import safe_url_for as u
from ..vars import LEGAL_NAME_PATTERN, STATS_PATH

router = APIRouter()
OK, ERROR, NA = 'ok', 'error', 'N/A'

REPORT_KEYS_SET = {'from_memory', 'status', 'pages', 'items', 'shutdown_reason', 'finish_reason', 'runtime',
                   'first_log_time', 'latest_log_time', 'log_categories', 'latest_matches'}
job_finished_key_dict = defaultdict(OrderedDict)
job_finished_report_dict = defaultdict(OrderedDict)


class LogHandler:
    def __init__(self, request, node, ctx, opt, project, spider, job):
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
        self.LOCAL_LOGS_DIR = self.s.get('LOCAL_SCRAPYD_LOGS_DIR', '')
        self.ENABLE_LOGPARSER = self.s.get('ENABLE_LOGPARSER', False)
        self.BACKUP_STATS_JSON_FILE = self.s.get('BACKUP_STATS_JSON_FILE', True)
        self.url = u'http://{}/logs/{}/{}/{}'.format(ctx.SCRAPYD_SERVER, project, spider, job)
        self.log_path = os.path.join(self.LOCAL_LOGS_DIR, project, spider, job)
        self.with_ext = request.query_params.get('with_ext', None)
        self.exts = [''] if self.with_ext else (self.s.get('SCRAPYD_LOG_EXTENSIONS', [])
                                                or ['.log', '.log.gz', '.txt', '.gz', ''])
        job_without_ext = get_job_without_ext(job) if self.with_ext else job
        self.job_without_ext = job_without_ext
        self.json_path = os.path.join(self.LOCAL_LOGS_DIR, project, spider, job_without_ext + '.json')
        self.json_url = u'http://{}/logs/{}/{}/{}.json'.format(ctx.SCRAPYD_SERVER, project, spider, job_without_ext)
        self.job_finished = request.query_params.get('job_finished', None)
        self.status_code = 0
        self.text = ''
        self.stats = {}
        self.logparser_valid = False
        self.backup_stats_valid = False
        self.utf8_realtime = opt == 'utf8'
        self.stats_realtime = bool(request.query_params.get('realtime')) if opt == 'stats' else False
        self.stats_logparser = opt == 'stats' and not self.stats_realtime
        self.report_logparser = opt == 'report'
        if self.utf8_realtime:
            self.flashes.append(('warning',
                                 "It's recommended to check out the latest log via: the Stats page >> View log >> Tail"))
        self.kwargs = dict(node=node, project=project, spider=spider, job=job_without_ext, url_refresh='', url_jump='')
        self.spider_path = self._mkdir_spider_path()
        self.backup_stats_path = os.path.join(self.spider_path, job_without_ext + '.json')

    def _mkdir_spider_path(self):
        node_path = os.path.join(STATS_PATH, re.sub(LEGAL_NAME_PATTERN, '-',
                                                    re.sub(r'[.:]', '_', self.ctx.SCRAPYD_SERVER)))
        path = os.path.join(node_path, self.project, self.spider)
        os.makedirs(path, exist_ok=True)
        return path

    def _read_local_stats(self):
        try:
            with io.open(self.json_path, 'r', encoding='utf-8') as f:
                js = json.loads(f.read())
        except Exception:
            return
        if js.get('logparser_version') != LOGPARSER_VERSION:
            self.flashes.append(('warning', "Mismatching logparser_version %s in local stats" % js.get('logparser_version')))
            return
        self.logparser_valid = True
        self.stats = js
        self.flashes.append(('info', "Using local stats: LogParser v%s, last updated at %s, %s" % (
            js['logparser_version'], js['last_update_time'], handle_slash(self.json_path))))

    async def _request_stats(self):
        status_code, js = await request_scrapyd(self.app.state.http_client, self.json_url, auth=self.ctx.AUTH, as_json=True)
        if status_code != 200:
            if self.ctx.IS_LOCAL_SCRAPYD_SERVER and self.ENABLE_LOGPARSER:
                self.flashes.append(('info', "Request to %s got code %s, wait until LogParser parses the log. " % (self.json_url, status_code)))
            else:
                self.flashes.append(('warning', ("'pip install logparser' on host '%s' and run command 'logparser'. "
                                                 "Or wait until LogParser parses the log. ") % self.ctx.SCRAPYD_SERVER))
            return
        if js.get('logparser_version') != LOGPARSER_VERSION:
            self.flashes.append(('warning', "'pip install --upgrade logparser' on host '%s' to update LogParser to v%s" % (
                self.ctx.SCRAPYD_SERVER, LOGPARSER_VERSION)))
            return
        self.logparser_valid = True
        self.stats = js
        self.flashes.append(('info', "LogParser v%s, last updated at %s, %s" % (
            js['logparser_version'], js['last_update_time'], self.json_url)))

    def _read_local_log(self):
        for ext in self.exts:
            log_path = self.log_path + ext
            if os.path.exists(log_path):
                if tarfile.is_tarfile(log_path):
                    break
                with io.open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    self.text = f.read()
                self.flashes.append(('info', "Using local logfile: %s" % handle_slash(log_path)))
                break

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

    def _load_backup(self):
        try:
            with io.open(self.backup_stats_path, 'r', encoding='utf-8') as f:
                js = json.loads(f.read())
        except Exception:
            return
        if js.get('logparser_version') != LOGPARSER_VERSION:
            self.flashes.append(('warning', "Mismatching logparser_version %s in backup stats" % js.get('logparser_version')))
            return
        self.logparser_valid = True
        self.backup_stats_valid = True
        self.stats = js
        self.flashes.append(('warning', "Using backup stats: LogParser v%s, last updated at %s, %s" % (
            js['logparser_version'], js['last_update_time'], handle_slash(self.backup_stats_path))))

    def _backup(self):
        try:
            with io.open(self.backup_stats_path, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(json_dumps(self.stats))
        except Exception:
            pass

    async def run(self):
        if self.report_logparser:
            try:
                self.stats = job_finished_report_dict[self.node][self.job_key]
                self.logparser_valid = True
                self.stats['from_memory'] = True
            except KeyError:
                pass
        if not self.logparser_valid and (self.stats_logparser or self.report_logparser):
            if self.ctx.IS_LOCAL_SCRAPYD_SERVER and self.LOCAL_LOGS_DIR:
                self._read_local_stats()
            if not self.logparser_valid:
                await self._request_stats()

        if not self.logparser_valid and not self.text:
            if self.ctx.IS_LOCAL_SCRAPYD_SERVER and self.LOCAL_LOGS_DIR:
                self._read_local_log()
            if not self.text:
                await self._request_log()
                if self.status_code != 200:
                    if self.stats_logparser or self.report_logparser:
                        self._load_backup()
                    if not self.backup_stats_valid and not self.report_logparser:
                        fail = 'scrapydweb/fail_mobileui.html' if self.ctx.USE_MOBILEUI else 'scrapydweb/fail.html'
                        return render(self.request, fail, self.node, self.ctx, flashes=self.flashes,
                                      page=dict(node=self.node, url=self.url, status_code=self.status_code, text=self.text))
                else:
                    self.url += self.exts[0]
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
        template = 'scrapydweb/%s%s.html' % (self.opt, '_mobileui' if self.ctx.USE_MOBILEUI else '')
        return render(self.request, template, self.node, self.ctx, page=self.kwargs, flashes=self.flashes)

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
            if self.BACKUP_STATS_JSON_FILE:
                self._backup()
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
                                                ui=self.ctx.UI, realtime='True' if self.stats_logparser else None)
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
                                                job_finished=self.job_finished, with_ext=self.with_ext, ui=self.ctx.UI)


async def log(request: Request, node: int, opt: str, project: str, spider: str, job: str,
              ctx: NodeContext = Depends(get_node_context)):
    return await LogHandler(request, node, ctx, opt, project, spider, job).run()


router.add_api_route('/{node:int}/log/{opt}/{project}/{spider}/{job}/', log,
                     methods=['GET', 'POST'], name='log')
