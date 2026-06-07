# coding: utf-8
"""CI/CD deploy endpoints.

- POST /api/deploy/push : multipart egg upload, authenticated by the
  X-Deploy-Token header (see middleware in app.py) -- for GitHub Actions etc.
- POST /api/deploy/git  : session-authenticated git-pull deploy: shallow-clone
  a repo, build the egg server-side, addversion to scrapyd.
"""
import logging
import os
import re
import subprocess
import tempfile
from shutil import rmtree

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..common import get_now_string
from ..context import NodeContext, get_node_context
from ..vars import LEGAL_NAME_PATTERN, STRICT_NAME_PATTERN

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/deploy')


def _sanitize(project, version):
    project = re.sub(STRICT_NAME_PATTERN, '_', project or '') or get_now_string()
    version = re.sub(LEGAL_NAME_PATTERN, '-', version or '') or get_now_string()
    return project, version


def _parse_nodes(raw, default):
    """'1,2' / [1, 2] -> sorted unique node list, falling back to [default]."""
    if isinstance(raw, (list, tuple)):
        nodes = sorted({int(n) for n in raw if str(n).isdigit()})
    else:
        nodes = sorted({int(n) for n in re.split(r'[,\s]+', str(raw or '').strip()) if n.isdigit()})
    return nodes or [default]


@router.post('/push', name='deploy.push')
async def deploy_push(request: Request, node: int = 1,
                      ctx: NodeContext = Depends(get_node_context)):
    """Token-authenticated egg push (CI pipelines)."""
    from .deploy import deploy_egg_to_nodes, record_deploy
    form = await request.form()
    upfile = form.get('egg') or form.get('file')
    if not upfile or not getattr(upfile, 'filename', ''):
        return JSONResponse({'status': 'error', 'message': "multipart field 'egg' required"},
                            status_code=400)
    project, version = _sanitize(form.get('project'), form.get('version'))
    nodes = _parse_nodes(form.get('nodes'), node)
    egg_bytes = await upfile.read()
    eggname = '%s_%s.egg' % (project, version)
    overall, results, first_js = await deploy_egg_to_nodes(
        request.app, nodes, project, version, egg_bytes, eggname)
    await record_deploy('push', project, version, eggname, overall, results=results,
                        actor='deploy-token')
    if overall == 'error':
        return JSONResponse(dict(status='error', alert='Fail to deploy project',
                                 js=first_js, message=first_js.get('message', ''),
                                 results=results), status_code=400)
    return JSONResponse(dict(status='ok', overall=overall, js=first_js, project=project,
                             version=version, eggname=eggname, selected_nodes=nodes,
                             first_selected_node=nodes[0], results=results))


def _redact(text, token):
    return text.replace(token, '***') if token else text


def _clone_and_build(repo, ref, token, project, version, testing):
    """Blocking git clone + egg build. Returns (project, version, eggname, egg_bytes) or error dict."""
    from .deploy import build_egg_from_cfg, _search_scrapy_cfg

    if not (repo.startswith('https://') or (testing and repo.startswith('file://'))):
        return dict(status='error', message='repo must be an https:// URL')

    url = repo
    if token and repo.startswith('https://'):
        url = repo.replace('https://', 'https://x-access-token:%s@' % token, 1)

    tmp = tempfile.mkdtemp(prefix='scrapydweb-git-')
    try:
        cmd = ['git', 'clone', '--depth', '1']
        if ref:
            cmd += ['--branch', ref]
        cmd += [url, tmp]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return dict(status='error', message='git clone failed: %s'
                        % _redact((r.stderr or r.stdout).strip()[-1000:], token))

        if not version:
            sha = subprocess.run(['git', '-C', tmp, 'rev-parse', '--short', 'HEAD'],
                                 capture_output=True, text=True)
            version = sha.stdout.strip() or get_now_string()
        project, version = _sanitize(project, version)

        cfg = _search_scrapy_cfg(tmp)
        if not cfg:
            return dict(status='error', message='scrapy.cfg not found in the repository')

        eggname = '%s_%s.egg' % (project, version)
        eggpath, err = build_egg_from_cfg(cfg, eggname)
        if err:
            err['message'] = _redact(err.get('message', ''), token)
            return err
        with open(eggpath, 'rb') as f:
            egg_bytes = f.read()
        return dict(status='built', project=project, version=version,
                    eggname=eggname, egg_bytes=egg_bytes)
    except subprocess.TimeoutExpired:
        return dict(status='error', message='git clone timed out')
    finally:
        rmtree(tmp, ignore_errors=True)


@router.post('/git', name='deploy.git')
async def deploy_git(request: Request, node: int = 1,
                     ctx: NodeContext = Depends(get_node_context)):
    """Clone a git repo, build the egg, deploy it (session auth)."""
    from .deploy import actor_from_request, deploy_egg_to_nodes, record_deploy
    body = await request.json()
    repo = str(body.get('repo') or '').strip()
    ref = str(body.get('ref') or '').strip()
    token = str(body.get('token') or '').strip()
    project = str(body.get('project') or '').strip()
    version = str(body.get('version') or '').strip()
    nodes = _parse_nodes(body.get('nodes'), node)
    if not repo:
        return JSONResponse({'status': 'error', 'message': 'repo is required'}, status_code=400)
    if not project:
        return JSONResponse({'status': 'error', 'message': 'project is required'}, status_code=400)

    actor = await actor_from_request(request)
    testing = bool(request.app.state.settings.get('TESTING'))
    built = await run_in_threadpool(_clone_and_build, repo, ref, token, project, version, testing)
    if built.get('status') != 'built':
        await record_deploy('git', project, version or None, None, 'error',
                            actor=actor, message=built.get('message', ''))
        return JSONResponse(built, status_code=400)

    overall, results, first_js = await deploy_egg_to_nodes(
        request.app, nodes, built['project'], built['version'],
        built['egg_bytes'], built['eggname'])
    await record_deploy('git', built['project'], built['version'], built['eggname'],
                        overall, results=results, actor=actor)
    if overall == 'error':
        return JSONResponse(dict(status='error', alert='Fail to deploy project',
                                 js=first_js, message=first_js.get('message', ''),
                                 results=results), status_code=400)
    return JSONResponse(dict(status='ok', overall=overall, js=first_js,
                             project=built['project'], version=built['version'],
                             eggname=built['eggname'], selected_nodes=nodes,
                             first_selected_node=nodes[0], results=results))


@router.get('/history', name='deploy.history')
async def deploy_history(request: Request, page: int = 1, per_page: int = 20,
                         project: str = '', repo_id: int = 0):
    """Recent deploy attempts, newest first."""
    import json
    from sqlalchemy import func, select
    from ..db import SessionLocal
    from ..models import DeployRecord

    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    query = select(DeployRecord)
    count_q = select(func.count()).select_from(DeployRecord)
    if project:
        query = query.filter_by(project=project)
        count_q = count_q.filter_by(project=project)
    if repo_id:
        query = query.filter_by(repo_id=repo_id)
        count_q = count_q.filter_by(repo_id=repo_id)
    async with SessionLocal() as s:
        total = (await s.execute(count_q)).scalar() or 0
        rows = (await s.execute(query.order_by(DeployRecord.id.desc())
                                .limit(per_page).offset((page - 1) * per_page))).scalars().all()
    records = []
    for r in rows:
        try:
            results = json.loads(r.results_json) if r.results_json else []
        except ValueError:
            results = []
        records.append(dict(
            id=r.id, source=r.source, project=r.project, version=r.version,
            eggname=r.eggname, status=r.status, actor=r.actor, repo_id=r.repo_id,
            message=r.message, results=results,
            created_at=str(r.created_at)[:19] if r.created_at else None,
            finished_at=str(r.finished_at)[:19] if r.finished_at else None,
        ))
    return JSONResponse({'status': 'ok', 'page': page, 'per_page': per_page,
                         'total': total, 'records': records})


# unused-import guard (os used by helpers via deploy module); keep flake quiet
_ = os
