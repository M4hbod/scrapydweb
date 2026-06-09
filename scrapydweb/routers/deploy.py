# coding: utf-8
"""Deploy project (ports views/operations/deploy.py)."""
from datetime import datetime
import glob
import io
import os
from pprint import pformat
import re
from shutil import copyfile, rmtree
from subprocess import CalledProcessError
import tarfile
import tempfile
import time
import zipfile

from configparser import Error as ScrapyCfgParseError

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from werkzeug.utils import secure_filename

from ..context import NodeContext, get_node_context
from ..common import get_now_string, json_dumps
from ..vars import DEPLOY_PATH, LEGAL_NAME_PATTERN, STRICT_NAME_PATTERN
from ..services.scrapyd_deploy import _build_egg, get_config
from ..services.deploy_utils import mkdir_p, slot

router = APIRouter()
OK = 'ok'
SCRAPY_CFG = """
[settings]
default = projectname.settings

[deploy]
url = http://localhost:6800/
project = projectname

"""
folder_project_dict = {}


def _modification_time(path):
    files = []
    in_top = True
    for dirpath, dirnames, filenames in os.walk(path):
        if in_top:
            in_top = False
            dirnames[:] = [d for d in dirnames if d not in ['build', 'project.egg-info']]
            filenames = [f for f in filenames if not (f.endswith('.egg') or f in ['setup.py', 'setup_backup.py'])]
        for f in filenames:
            files.append(os.path.join(dirpath, f))
    return max([os.path.getmtime(f) for f in files] or [time.time()])


def scan_projects_dir(app):
    """Scan SCRAPY_PROJECTS_DIR for deployable scrapy projects (shared with apiv2)."""
    from ..vars import DEMO_PROJECTS_PATH
    projects_dir = app.state.settings.get('SCRAPY_PROJECTS_DIR', '') or DEMO_PROJECTS_PATH

    cfg_list = sorted(glob.glob(os.path.join(projects_dir, '*', 'scrapy.cfg')), key=lambda x: x.lower())
    project_paths = [os.path.dirname(i) for i in cfg_list]
    folders = [os.path.basename(i) for i in project_paths]
    timestamps = [_modification_time(p) for p in project_paths]
    modification_times = [datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H_%M_%S') for ts in timestamps]
    latest_folder = folders[timestamps.index(max(timestamps))] if timestamps else ''

    projects = []
    for idx, scrapy_cfg in enumerate(cfg_list):
        key = '%s (%s)' % (folders[idx], modification_times[idx])
        project = folder_project_dict.get(key, '')
        if not project:
            project = folders[idx]
            try:
                project = get_config(scrapy_cfg).get('deploy', 'project')
            except ScrapyCfgParseError:
                pass
            project = project or folders[idx]
            folder_project_dict[key] = project
        projects.append(project)
    return dict(projects_dir=projects_dir, folders=folders, projects=projects,
                modification_times=modification_times, latest_folder=latest_folder)


def _uncompress(filepath):
    tmpdir = tempfile.mkdtemp(prefix="scrapydweb-uncompress-")
    if zipfile.is_zipfile(filepath):
        with zipfile.ZipFile(filepath, 'r') as f:
            f.extractall(tmpdir)
    else:
        with tarfile.open(filepath, 'r') as tar:
            tar.extractall(tmpdir)
    return tmpdir


def _search_scrapy_cfg(search_path):
    for dirpath, dirnames, filenames in os.walk(search_path):
        cfg = os.path.abspath(os.path.join(dirpath, 'scrapy.cfg'))
        if os.path.exists(cfg):
            return cfg
    return ''


async def _addversion(client, server, auth, project, version, egg_bytes):
    url = 'http://%s/addversion.json' % server
    try:
        r = await client.post(url, data={'project': project, 'version': version},
                              files={'egg': ('%s.egg' % project, egg_bytes)},
                              auth=tuple(auth) if auth else None, timeout=60)
    except Exception as err:
        return -1, dict(url=url, status_code=-1, status='error', message=str(err))
    try:
        js = r.json()
    except ValueError:
        js = dict(status='error', message=r.text)
    js.setdefault('status', 'N/A')
    js['status_code'] = r.status_code
    return r.status_code, js



def build_egg_from_cfg(cfg, eggname):
    """Build an egg from a scrapy.cfg location. Returns (eggpath, error_dict|None)."""
    eggpath = os.path.join(DEPLOY_PATH, eggname)
    try:
        egg, td = _build_egg(cfg)
        copyfile(egg, os.path.join(os.path.dirname(cfg), eggname))
        copyfile(egg, eggpath)
        rmtree(td)
    except ScrapyCfgParseError as err:
        return None, dict(status='error', alert='Fail to deploy project:',
                          text=str(err),
                          tip="Check the content of the 'scrapy.cfg' file in your project directory. ",
                          message="# The 'scrapy.cfg' file should be like:\n%s" % SCRAPY_CFG)
    except CalledProcessError as err:
        # the real build output is attached by _build_egg; show it instead of just "exit status 1"
        stderr_tail = getattr(err, 'stderr_tail', '') or ''
        text = '%s\n\n%s' % (str(err), stderr_tail) if stderr_tail else str(err)
        return None, dict(status='error', alert='Fail to deploy project:',
                          text=text,
                          tip='Check scrapy.cfg, or build the egg yourself. ',
                          message="# The 'scrapy.cfg' file should be like:\n%s" % SCRAPY_CFG)
    return eggpath, None


def _node_targets(settings, nodes):
    """Resolve node numbers to [(node, server, auth)], dropping out-of-range nodes."""
    servers = settings.get('SCRAPYD_SERVERS', []) or []
    auths = settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None] * len(servers)
    targets = []
    for n in nodes:
        if 1 <= n <= len(servers):
            auth = auths[n - 1] if n - 1 < len(auths) else None
            targets.append((n, servers[n - 1], auth))
    return targets


async def deploy_egg_to_nodes(app, nodes, project, version, egg_bytes, eggname):
    """Store the egg once, addversion to every target node concurrently.

    Returns (overall, results, first_js): overall in ok|partial|error, results is
    [{node, server, status, status_code, message}], first_js the raw addversion
    response of the first target (legacy response shape).
    """
    import asyncio

    eggpath = os.path.join(DEPLOY_PATH, eggname)
    with open(eggpath, 'wb') as f:
        f.write(egg_bytes)
    slot.add_egg(eggname, egg_bytes)

    targets = _node_targets(app.state.settings, nodes)
    if not targets:
        return 'error', [], dict(status='error', message='no valid target nodes: %s' % nodes)

    responses = await asyncio.gather(*[
        _addversion(app.state.http_client, server, auth, project, version, egg_bytes)
        for _n, server, auth in targets])
    results, ok_count = [], 0
    for (n, server, _auth), (status_code, js) in zip(targets, responses):
        ok = js.get('status') == OK
        ok_count += ok
        results.append(dict(node=n, server=server, status='ok' if ok else 'error',
                            status_code=status_code, message=js.get('message', '')))
    overall = 'ok' if ok_count == len(targets) else ('partial' if ok_count else 'error')
    return overall, results, responses[0][1]


async def record_deploy(source, project, version, eggname, status, results=None,
                        actor=None, repo_id=None, message=''):
    """Insert a DeployRecord audit row; returns its id (None on failure)."""
    from ..db import SessionLocal
    from ..models import DeployRecord
    try:
        async with SessionLocal() as s:
            rec = DeployRecord(
                source=source, project=project, version=version, eggname=eggname,
                status=status, actor=actor, repo_id=repo_id, message=message or None,
                results_json=json_dumps(results) if results is not None else None,
                finished_at=None if status == 'pending' else datetime.now())
            s.add(rec)
            await s.commit()
            return rec.id
    except Exception as err:
        import logging
        logging.getLogger(__name__).warning('Fail to record deploy: %s', err)
        return None


async def finish_deploy_record(record_id, status, results=None, version=None,
                               eggname=None, message=''):
    """Finalize a pending DeployRecord (webhook deploys run in the background)."""
    if record_id is None:
        return
    from sqlalchemy import select
    from ..db import SessionLocal
    from ..models import DeployRecord
    try:
        async with SessionLocal() as s:
            rec = (await s.execute(
                select(DeployRecord).filter_by(id=record_id))).scalar_one_or_none()
            if rec is None:
                return
            rec.status = status
            if results is not None:
                rec.results_json = json_dumps(results)
            if version:
                rec.version = version
            if eggname:
                rec.eggname = eggname
            if message:
                rec.message = message
            rec.finished_at = datetime.now()
            await s.commit()
    except Exception as err:
        import logging
        logging.getLogger(__name__).warning('Fail to finalize deploy record #%s: %s', record_id, err)


async def actor_from_request(request):
    """Username behind the session cookie, or None (token/webhook callers)."""
    from sqlalchemy import select
    from ..auth import SESSION_COOKIE, verify_session_token
    from ..db import SessionLocal
    from ..models import User
    token = request.cookies.get(SESSION_COOKIE, '')
    uid = verify_session_token(token, request.app.state.settings.get('SECRET_KEY', ''))
    if uid is None:
        return None
    try:
        async with SessionLocal() as s:
            user = (await s.execute(select(User).filter_by(id=uid))).scalar_one_or_none()
        return user.username if user else None
    except Exception:
        return None


async def deploy_egg_bytes(app, server, auth, project, version, egg_bytes, eggname):
    """Store + addversion an egg (single node). Returns the standard deploy JSON dict."""
    eggpath = os.path.join(DEPLOY_PATH, eggname)
    with open(eggpath, 'wb') as f:
        f.write(egg_bytes)
    slot.add_egg(eggname, egg_bytes)
    status_code, js = await _addversion(app.state.http_client, server, auth,
                                        project, version, egg_bytes)
    if js['status'] != OK:
        return dict(status='error', alert='Fail to deploy project, got status: ' + js['status'],
                    js=js, message=js.get('message', ''))
    return dict(status='ok', js=js, project=project, version=version,
                eggname=eggname, selected_nodes=[], first_selected_node=0)


async def deploy_upload(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    settings = app.state.settings
    form = await request.form()

    selected_amount = int(form.get('checked_amount') or 0)
    nodes_field = (form.get('nodes') or '').strip()  # "1,3" -- SPA multi-node deploy
    if nodes_field:
        selected_nodes = sorted({int(n) for n in re.split(r'[,\s]+', nodes_field) if n.isdigit()})
        selected_nodes = [n for n in selected_nodes if 1 <= n <= ctx.SCRAPYD_SERVERS_AMOUNT]
        first = selected_nodes[0] if selected_nodes else node
        target_nodes = selected_nodes or [node]
    elif selected_amount:
        selected_nodes = [n for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1) if form.get(str(n)) == 'on']
        first = selected_nodes[0]
        target_nodes = selected_nodes
    else:
        selected_nodes = []
        first = 0
        target_nodes = [node]

    project = re.sub(STRICT_NAME_PATTERN, '_', form.get('project', '') or '') or get_now_string()
    version = re.sub(LEGAL_NAME_PATTERN, '-', form.get('version', '') or '') or get_now_string()

    eggname = ''
    eggpath = ''
    scrapy_cfg_not_found = False
    scrapy_cfg_parse_error = ''
    build_egg_error = ''
    searched = []

    upfile = form.get('file')
    if upfile and getattr(upfile, 'filename', ''):
        filename = secure_filename(upfile.filename)
        if filename in ['egg', 'zip', 'tar.gz']:
            filename = '%s_%s.%s' % (project, version, filename)
        else:
            filename = '%s_%s_from_file_%s' % (project, version, filename)
        content = await upfile.read()
        if filename.endswith('egg'):
            # canonical name: the code viewer resolves {project}_{version}.egg
            eggname = '%s_%s.egg' % (project, version)
            eggpath = os.path.join(DEPLOY_PATH, eggname)
            with open(eggpath, 'wb') as f:
                f.write(content)
        else:
            filepath = os.path.join(DEPLOY_PATH, filename)
            with open(filepath, 'wb') as f:
                f.write(content)
            tmpdir = _uncompress(filepath)
            cfg = _search_scrapy_cfg(tmpdir)
            searched.append(tmpdir)
            if not cfg:
                scrapy_cfg_not_found = True
            else:
                eggname = '%s_%s.egg' % (project, version)
                eggpath = os.path.join(DEPLOY_PATH, eggname)
                try:
                    egg, td = _build_egg(cfg)
                    copyfile(egg, os.path.join(os.path.dirname(cfg), eggname))
                    copyfile(egg, eggpath)
                    rmtree(td)
                except ScrapyCfgParseError as err:
                    scrapy_cfg_parse_error = str(err)
                except CalledProcessError as err:
                    build_egg_error = str(err)
    else:
        folder = form.get('folder', '')
        from ..vars import DEMO_PROJECTS_PATH
        projects_dir = settings.get('SCRAPY_PROJECTS_DIR', '') or DEMO_PROJECTS_PATH
        project_path = os.path.join(projects_dir, folder)
        cfg = _search_scrapy_cfg(project_path)
        searched.append(project_path)
        if not cfg:
            scrapy_cfg_not_found = True
        else:
            eggname = '%s_%s.egg' % (project, version)
            eggpath = os.path.join(DEPLOY_PATH, eggname)
            try:
                egg, td = _build_egg(cfg)
                copyfile(egg, os.path.join(os.path.dirname(cfg), eggname))
                copyfile(egg, eggpath)
                rmtree(td)
            except ScrapyCfgParseError as err:
                scrapy_cfg_parse_error = str(err)
            except CalledProcessError as err:
                build_egg_error = str(err)

    if scrapy_cfg_not_found or scrapy_cfg_parse_error or build_egg_error:
        alert = "Multinode deployment terminated:" if selected_amount > 1 else "Fail to deploy project:"
        if scrapy_cfg_not_found:
            text = "scrapy.cfg not found"
            tip = "Make sure that the 'scrapy.cfg' file resides in your project directory. "
            message = "scrapy_cfg_searched_paths:\n%s" % pformat(searched)
        elif scrapy_cfg_parse_error:
            text = scrapy_cfg_parse_error
            tip = "Check the content of the 'scrapy.cfg' file in your project directory. "
            message = "# The 'scrapy.cfg' file in your project directory should be like:\n%s" % SCRAPY_CFG
        else:
            text = build_egg_error
            tip = ("Check the content of the 'scrapy.cfg' file in your project directory. "
                   "Or build the egg file by yourself instead. ")
            message = "# The 'scrapy.cfg' file in your project directory should be like:\n%s" % SCRAPY_CFG
        return JSONResponse(dict(status='error', alert=alert, text=text, tip=tip, message=message))

    with io.open(eggpath, 'rb') as f:
        content = f.read()
    overall, results, first_js = await deploy_egg_to_nodes(
        app, target_nodes, project, version, content, eggname)
    source = 'file' if (upfile and getattr(upfile, 'filename', '')) else 'folder'
    await record_deploy(source, project, version, eggname, overall, results=results,
                        actor=await actor_from_request(request))

    if overall == 'error':
        if len(target_nodes) > 1:
            alert = "Multinode deployment failed on every node, first node returned status: " + first_js['status']
        else:
            alert = "Fail to deploy project, got status: " + first_js['status']
        return JSONResponse(dict(status='error', alert=alert, js=first_js,
                                 message=first_js.get('message', ''), results=results))

    return JSONResponse(dict(status='ok', overall=overall, js=first_js, project=project,
                             version=version, eggname=eggname, selected_nodes=selected_nodes,
                             first_selected_node=first, results=results))


async def deploy_xhr(request: Request, node: int, eggname: str, project: str, version: str,
                     ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    content = slot.egg.get(eggname)
    if not content:
        with io.open(os.path.join(DEPLOY_PATH, eggname), 'rb') as f:
            content = f.read()
    status_code, js = await _addversion(app.state.http_client, ctx.SCRAPYD_SERVER, ctx.AUTH, project, version, content)
    from fastapi.responses import JSONResponse
    return JSONResponse(js)


router.add_api_route('/{node:int}/deploy/upload/', deploy_upload, methods=['POST'], name='deploy.upload')
router.add_api_route('/{node:int}/deploy/xhr/{eggname}/{project}/{version}/', deploy_xhr,
                     methods=['GET', 'POST'], name='deploy.xhr')
