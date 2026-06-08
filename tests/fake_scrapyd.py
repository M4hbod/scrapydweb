# coding: utf-8
"""In-process fake scrapyd for the fast test suite.

A tiny FastAPI app served by uvicorn in a daemon thread on a random port.
Both the app's async httpx client (services/scrapyd.request_scrapyd) and the
sync requests.Session (services/logstats, services/tasks, services/alerts,
services/job_versions) hit it unmodified -- zero HTTP monkeypatching.

Jobs scheduled via /schedule.json land *finished* instantly (instant_finish,
default) with a canned real scrapy log attached, so lifecycle tests need no
polling. State is plain Python -- tests in the same process mutate
``fake.state`` directly; an unauthenticated ``/__test__/...`` control API
exists for symmetry.
"""
import base64
import os
import threading
import time
import uuid
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

AUTH = ('admin', '12345')
PROJECT = 'ScrapydWeb_demo'
SPIDER = 'test'
DEMO_JOBID = 'ScrapydWeb_demo'
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def _canned_log():
    with open(os.path.join(_DATA_DIR, '%s.log' % PROJECT), encoding='utf-8') as f:
        return f.read()


class FakeScrapydState(object):
    def __init__(self):
        self.reset()

    def reset(self):
        finished_log = _canned_log()
        # same trick as the legacy setup_env: drop finish_reason -> logparser sees it as running
        unfinished_log = finished_log.replace("'finish_reason'", "'finish_reason_removed'")
        self.finished_log = finished_log
        self.unfinished_log = unfinished_log

        self.projects = {}      # project -> {version: egg_bytes} (insertion order = version order)
        self.spiders = {}       # project -> [spider, ...]
        self.jobs = []          # {project, spider, job, pid, start, finish, runtime}
        self.logs = {}          # (project, spider, jobid) -> log text  (served as <jobid>.log)
        self.items = {}         # (project, spider, filename) -> bytes
        self.counters = {'cancel': {}, 'requests': {}}
        self.fail_next = {}     # endpoint -> remaining 500s
        self.naive_range = False
        self.instant_finish = True
        # pre-seed the demo logs the legacy tests expect on the scrapyd side
        self.logs[(PROJECT, SPIDER, DEMO_JOBID)] = finished_log
        self.logs[(PROJECT, SPIDER, '%s_unfinished' % DEMO_JOBID)] = unfinished_log

    # ---- helpers
    def bump(self, endpoint):
        self.counters['requests'][endpoint] = self.counters['requests'].get(endpoint, 0) + 1

    def should_fail(self, endpoint):
        n = self.fail_next.get(endpoint, 0)
        if n > 0:
            self.fail_next[endpoint] = n - 1
            return True
        return False

    def add_job(self, project, spider, jobid, finished=True, log=None):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        job = dict(project=project, spider=spider, job=jobid, pid='6800',
                   start=now, finish=now if finished else '', runtime='0:00:01' if finished else '')
        self.jobs.append(job)
        self.logs[(project, spider, jobid)] = log if log is not None else (
            self.finished_log if finished else self.unfinished_log)
        return job

    def finish_job(self, project, spider, jobid):
        for job in self.jobs:
            if (job['project'], job['spider'], job['job']) == (project, spider, jobid) and not job['finish']:
                job['finish'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                job['runtime'] = '0:00:01'
        self.logs[(project, spider, jobid)] = self.finished_log


def build_app(state):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authed(request):
        header = request.headers.get('authorization', '')
        if not header.lower().startswith('basic '):
            return False
        try:
            user, _, pwd = base64.b64decode(header.split(None, 1)[1]).decode().partition(':')
        except Exception:
            return False
        return (user, pwd) == AUTH

    def gate(request, endpoint):
        """Returns an early Response or None. Also counts the request."""
        state.bump(endpoint)
        if not authed(request):
            return Response(status_code=401, content='Unauthorized')
        if state.should_fail(endpoint):
            return PlainTextResponse('fake scrapyd: forced failure', status_code=500)
        return None

    # ------------------------------------------------------------- json api
    @app.get('/daemonstatus.json')
    async def daemonstatus(request: Request):
        early = gate(request, 'daemonstatus')
        if early:
            return early
        running = len([j for j in state.jobs if j['start'] and not j['finish']])
        finished = len([j for j in state.jobs if j['finish']])
        return JSONResponse(dict(status='ok', pending=0, running=running,
                                 finished=finished, node_name='fake-scrapyd'))

    @app.get('/listprojects.json')
    async def listprojects(request: Request):
        early = gate(request, 'listprojects')
        if early:
            return early
        return JSONResponse(dict(status='ok', projects=list(state.projects),
                                 node_name='fake-scrapyd'))

    @app.get('/listversions.json')
    async def listversions(request: Request, project: str = ''):
        early = gate(request, 'listversions')
        if early:
            return early
        if project not in state.projects:
            return JSONResponse(dict(status='error', node_name='fake-scrapyd',
                                     message="no active project"))
        return JSONResponse(dict(status='ok', versions=list(state.projects[project]),
                                 node_name='fake-scrapyd'))

    @app.get('/listspiders.json')
    async def listspiders(request: Request, project: str = '', _version: str = ''):
        early = gate(request, 'listspiders')
        if early:
            return early
        if project not in state.projects:
            return JSONResponse(dict(status='error', node_name='fake-scrapyd',
                                     message="no active project"))
        return JSONResponse(dict(status='ok', spiders=state.spiders.get(project, [SPIDER]),
                                 node_name='fake-scrapyd'))

    @app.get('/listjobs.json')
    async def listjobs(request: Request, project: str = ''):
        early = gate(request, 'listjobs')
        if early:
            return early
        running = [dict(id=j['job'], spider=j['spider'], start_time=j['start'])
                   for j in state.jobs if j['start'] and not j['finish']
                   and (not project or j['project'] == project)]
        finished = [dict(id=j['job'], spider=j['spider'], start_time=j['start'], end_time=j['finish'])
                    for j in state.jobs if j['finish'] and (not project or j['project'] == project)]
        return JSONResponse(dict(status='ok', pending=[], running=running, finished=finished,
                                 node_name='fake-scrapyd'))

    @app.post('/schedule.json')
    async def schedule(request: Request):
        early = gate(request, 'schedule')
        if early:
            return early
        form = await request.form()
        project, spider = form.get('project', ''), form.get('spider', '')
        if project not in state.projects:
            return JSONResponse(dict(status='error', node_name='fake-scrapyd',
                                     message="Scrapy VersionError: no active project"))
        jobid = form.get('jobid') or uuid.uuid4().hex
        state.add_job(project, spider, jobid, finished=state.instant_finish)
        return JSONResponse(dict(status='ok', jobid=jobid, node_name='fake-scrapyd'))

    @app.post('/cancel.json')
    async def cancel(request: Request):
        early = gate(request, 'cancel')
        if early:
            return early
        form = await request.form()
        project, jobid = form.get('project', ''), form.get('job', '')
        key = (project, jobid)
        state.counters['cancel'][key] = state.counters['cancel'].get(key, 0) + 1
        prevstate = 'running'
        for j in state.jobs:
            if j['project'] == project and j['job'] == jobid:
                state.finish_job(j['project'], j['spider'], jobid)
        return JSONResponse(dict(status='ok', prevstate=prevstate, node_name='fake-scrapyd'))

    @app.post('/addversion.json')
    async def addversion(request: Request):
        early = gate(request, 'addversion')
        if early:
            return early
        form = await request.form()
        project, version = form.get('project', ''), form.get('version', '')
        egg = form.get('egg')
        egg_bytes = await egg.read() if egg is not None and hasattr(egg, 'read') else b''
        state.projects.setdefault(project, {})[version] = egg_bytes
        state.spiders.setdefault(project, [SPIDER])
        return JSONResponse(dict(status='ok', project=project, version=version,
                                 spiders=len(state.spiders[project]), node_name='fake-scrapyd'))

    @app.post('/delversion.json')
    async def delversion(request: Request):
        early = gate(request, 'delversion')
        if early:
            return early
        form = await request.form()
        project, version = form.get('project', ''), form.get('version', '')
        versions = state.projects.get(project, {})
        if version in versions:
            versions.pop(version)
            if not versions:
                state.projects.pop(project, None)
                state.spiders.pop(project, None)
            return JSONResponse(dict(status='ok', node_name='fake-scrapyd'))
        return JSONResponse(dict(status='error', node_name='fake-scrapyd',
                                 message='version not found'))

    @app.post('/delproject.json')
    async def delproject(request: Request):
        early = gate(request, 'delproject')
        if early:
            return early
        form = await request.form()
        project = form.get('project', '')
        state.projects.pop(project, None)
        state.spiders.pop(project, None)
        return JSONResponse(dict(status='ok', node_name='fake-scrapyd'))

    # ------------------------------------------------------------- jobs html
    @app.get('/jobs')
    async def jobs_html(request: Request):
        early = gate(request, 'jobs')
        if early:
            return early
        # scrapyd lists pending first, then running, then finished -- the
        # parser's unique-constraint pass depends on this ordering
        ordered = ([j for j in state.jobs if not j['start']]
                   + [j for j in state.jobs if j['start'] and not j['finish']]
                   + [j for j in state.jobs if j['finish']])
        rows = []
        for j in ordered:
            rows.append(
                '<tr><td>{project}</td><td>{spider}</td><td>{job}</td><td>{pid}</td>'
                '<td>{start}</td><td>{runtime}</td><td>{finish}</td>'
                '<td><a href="/logs/{project}/{spider}/{job}.log">Log</a></td>'
                '<td><a href="/items/{project}/{spider}/{job}.jl">Items</a></td></tr>'.format(**j))
        html = ('<html><head><title>Scrapyd</title></head><body><h1>Jobs</h1>'
                '<table border="1"><thead><tr><th>Project</th><th>Spider</th><th>Job</th>'
                '<th>PID</th><th>Start</th><th>Runtime</th><th>Finish</th><th>Log</th>'
                '<th>Items</th></tr></thead><tbody>%s</tbody></table></body></html>'
                % ''.join(rows))
        return HTMLResponse(html)

    # ------------------------------------------------------------- files
    def _serve_bytes(request, content, media_type):
        rng = request.headers.get('range', '')
        if rng.startswith('bytes=') and not state.naive_range:
            # only the bytes=0-0 probe is used by the collector
            return Response(content=content[:1], status_code=206, media_type=media_type,
                            headers={'Content-Range': 'bytes 0-0/%d' % len(content)})
        return Response(content=content, media_type=media_type)

    @app.get('/logs/{project}/{spider}/{filename}')
    async def serve_log(request: Request, project: str, spider: str, filename: str):
        early = gate(request, 'logs')
        if early:
            return early
        if not filename.endswith('.log'):
            return PlainTextResponse('not found', status_code=404)
        jobid = filename[:-len('.log')]
        text = state.logs.get((project, spider, jobid))
        if text is None:
            return PlainTextResponse('not found', status_code=404)
        return _serve_bytes(request, text.encode('utf-8'), 'text/plain; charset=utf-8')

    @app.get('/items/{project}/{spider}/{filename}')
    async def serve_items(request: Request, project: str, spider: str, filename: str):
        early = gate(request, 'items')
        if early:
            return early
        content = state.items.get((project, spider, filename))
        if content is None:
            return PlainTextResponse('not found', status_code=404)
        return _serve_bytes(request, content, 'application/octet-stream')

    # ------------------------------------------------------------- control api (no auth)
    @app.post('/__test__/reset')
    async def control_reset():
        state.reset()
        return JSONResponse({'status': 'ok'})

    @app.post('/__test__/jobs')
    async def control_jobs(request: Request):
        body = await request.json()
        job = state.add_job(body['project'], body['spider'], body['job'],
                            finished=body.get('finished', True), log=body.get('log'))
        return JSONResponse({'status': 'ok', 'job': job})

    @app.post('/__test__/finish/{project}/{spider}/{jobid}')
    async def control_finish(project: str, spider: str, jobid: str):
        state.finish_job(project, spider, jobid)
        return JSONResponse({'status': 'ok'})

    @app.post('/__test__/fail_next')
    async def control_fail_next(request: Request):
        body = await request.json()
        state.fail_next[body['endpoint']] = int(body.get('times', 1))
        return JSONResponse({'status': 'ok'})

    @app.post('/__test__/config')
    async def control_config(request: Request):
        body = await request.json()
        for key in ('naive_range', 'instant_finish'):
            if key in body:
                setattr(state, key, bool(body[key]))
        return JSONResponse({'status': 'ok'})

    return app


class FakeScrapyd(object):
    """Session-scoped runner: uvicorn in a daemon thread on a random port."""

    def __init__(self):
        self.state = FakeScrapydState()
        self.app = build_app(self.state)
        config = uvicorn.Config(self.app, host='127.0.0.1', port=0, log_level='warning')
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError('fake scrapyd failed to start')
            time.sleep(0.01)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.address = '127.0.0.1:%d' % port
        return self

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)
