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
from fastapi.responses import HTMLResponse
from ..responses import redirect as _redirect
from werkzeug.utils import secure_filename

from ..context import NodeContext, get_node_context
from ..common import get_now_string, json_dumps
from ..templating import render
from ..urls import safe_url_for as u, url_for
from ..vars import DEPLOY_PATH, LEGAL_NAME_PATTERN, STRICT_NAME_PATTERN
from ..views.operations.scrapyd_deploy import _build_egg, get_config
from ..views.operations.utils import mkdir_p, slot

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


def _fail(ctx):
    return 'scrapydweb/fail_mobileui.html' if ctx.USE_MOBILEUI else 'scrapydweb/fail.html'


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


async def deploy(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    projects_dir = (app.state.settings.get('SCRAPY_PROJECTS_DIR', '')
                    or app.state.settings.get('DEMO_PROJECTS_PATH', '')) or ''
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

    page = dict(
        node=node, url='http://%s/addversion.json' % ctx.SCRAPYD_SERVER,
        url_projects=u(app, 'projects', node=node), selected_nodes=[],
        folders=folders, projects=projects, modification_times=modification_times,
        latest_folder=latest_folder, SCRAPY_PROJECTS_DIR=projects_dir.replace('\\', '/'),
        url_servers=u(app, 'servers', node=node, opt='deploy'),
        url_deploy_upload=u(app, 'deploy.upload', node=node),
    )
    return render(request, 'scrapydweb/deploy.html', node, ctx, page=page)


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


async def deploy_upload(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    settings = app.state.settings
    servers = ctx.SCRAPYD_SERVERS
    auths = settings.get('SCRAPYD_SERVERS_AUTHS', []) or [None]
    form = await request.form()

    selected_amount = int(form.get('checked_amount') or 0)
    if selected_amount:
        selected_nodes = [n for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1) if form.get(str(n)) == 'on']
        first = selected_nodes[0]
        target_server = servers[first - 1]
        target_auth = auths[first - 1]
    else:
        selected_nodes = []
        first = 0
        target_server = ctx.SCRAPYD_SERVER
        target_auth = ctx.AUTH

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
            eggname = filename
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
                eggname = re.sub(r'(\.zip|\.tar\.gz)$', '.egg', filename)
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
        projects_dir = settings.get('SCRAPY_PROJECTS_DIR', '')
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
        return render(request, _fail(ctx), node, ctx,
                      page=dict(node=node, alert=alert, text=text, tip=tip, message=message))

    with io.open(eggpath, 'rb') as f:
        content = f.read()
    slot.add_egg(eggname, content)
    status_code, js = await _addversion(app.state.http_client, target_server, target_auth, project, version, content)

    if js['status'] != OK:
        if selected_amount > 1:
            alert = "Multinode deployment terminated, since the first selected node returned status: " + js['status']
        else:
            alert = "Fail to deploy project, got status: " + js['status']
        message = js.get('message', '')
        if message:
            js['message'] = 'See details below'
        return render(request, _fail(ctx), node, ctx,
                      page=dict(node=node, alert=alert, text=json_dumps(js), message=message))

    if selected_amount == 0:
        return _redirect(url_for(app, 'schedule', node=node, project=project, version=version))
    page = dict(
        node=node, selected_nodes=selected_nodes, first_selected_node=first, js=js,
        project=project, version=version,
        url_projects_first_selected_node=u(app, 'projects', node=first),
        url_projects_list=[u(app, 'projects', node=n) for n in range(1, ctx.SCRAPYD_SERVERS_AMOUNT + 1)],
        url_xhr=u(app, 'deploy.xhr', node=node, eggname=eggname, project=project, version=version),
        url_schedule=u(app, 'schedule', node=node, project=project, version=version),
        url_servers=u(app, 'servers', node=node, opt='schedule', project=project, version_job=version),
    )
    return render(request, 'scrapydweb/deploy_results.html', node, ctx, page=page)


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


router.add_api_route('/{node:int}/deploy/', deploy, methods=['GET'], name='deploy')
router.add_api_route('/{node:int}/deploy/upload/', deploy_upload, methods=['POST'], name='deploy.upload')
router.add_api_route('/{node:int}/deploy/xhr/{eggname}/{project}/{version}/', deploy_xhr,
                     methods=['GET', 'POST'], name='deploy.xhr')
