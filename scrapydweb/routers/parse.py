# coding: utf-8
"""Parse uploaded logfile (ports views/utilities/parse.py)."""
import io
import os
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from logparser import parse
from werkzeug.utils import secure_filename

from ..common import get_now_string
from ..context import NodeContext, get_node_context
from ..templating import render
from ..urls import url_for
from ..vars import PARSE_PATH

router = APIRouter()
ALLOWED_EXTENSIONS = {'log', 'txt'}
NA = 'N/A'


@router.get('/parse/source/{filename}', name='parse.source')
async def source(filename: str):
    return FileResponse(os.path.join(PARSE_PATH, filename), media_type='text/plain')


async def upload(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    if request.method == 'POST':
        form = await request.form()
        file = form.get('file')
        fail = 'scrapydweb/parse.html'
        if not file or not getattr(file, 'filename', ''):
            return render(request, fail, node, ctx, page=dict(
                node=node, url_parse_demo=url_for(app, 'parse.uploaded', node=node, filename='ScrapydWeb_demo.log')),
                flashes=[('warning', 'No file selected')])
        if file.filename.rpartition('.')[-1] not in ALLOWED_EXTENSIONS:
            return render(request, fail, node, ctx, page=dict(
                node=node, url_parse_demo=url_for(app, 'parse.uploaded', node=node, filename='ScrapydWeb_demo.log')),
                flashes=[('warning', 'Only file type of %s is supported' % ALLOWED_EXTENSIONS)])
        filename = secure_filename(file.filename)
        if filename in ALLOWED_EXTENSIONS:
            filename = '%s.%s' % (get_now_string(), filename)
        with open(os.path.join(PARSE_PATH, filename), 'wb') as f:
            f.write(await file.read())
        return RedirectResponse(url_for(app, 'parse.uploaded', node=node, filename=filename), status_code=302)
    return render(request, 'scrapydweb/parse.html', node, ctx, page=dict(
        node=node, url_parse_demo=url_for(app, 'parse.uploaded', node=node, filename='ScrapydWeb_demo.log')))


def _job_info(text, filename):
    m_project = re.search(r'\(bot:\s(.+?)\)', text)
    project = m_project.group(1) if m_project else NA
    m_spider = re.search(r'\[([^.]+?)\]\s+(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)', text)
    spider = m_spider.group(1) if m_spider else NA
    m_job = re.search(r'LOG_FILE.*?([\w-]+)\.(?:log|txt)', text)
    job = m_job.group(1) if m_job else (filename.rpartition('.')[0] or filename)
    return project, spider, job


async def uploaded(request: Request, node: int, filename: str,
                   ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    try:
        with io.open(os.path.join(PARSE_PATH, filename), encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except Exception as err:
        fail = 'scrapydweb/fail_mobileui.html' if ctx.USE_MOBILEUI else 'scrapydweb/fail.html'
        return render(request, fail, node, ctx, page=dict(
            node=node, alert="An error occurred when reading the uploaded logfile",
            text='%s\n%s' % (err.__class__.__name__, err)))
    project, spider, job = _job_info(text, filename)
    page = dict(project=project, spider=spider, job=job,
                url_source=url_for(app, 'parse.source', filename=filename), node=node)
    page.update(parse(text))
    return render(request, 'scrapydweb/stats.html', node, ctx, page=page)


router.add_api_route('/{node:int}/parse/upload/', upload, methods=['GET', 'POST'], name='parse.upload')
router.add_api_route('/{node:int}/parse/uploaded/{filename}/', uploaded, methods=['GET'], name='parse.uploaded')
