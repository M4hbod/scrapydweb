# coding: utf-8
"""Send text via Slack/Telegram/Email (ports views/utilities/send_text.py)."""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..common import get_now_string, json_dumps
from ..context import NodeContext, get_node_context
from ..services.scrapyd import OK, ERROR, request_scrapyd
from ..templating import render
from ..urls import url_for
from ..utils.send_email import send_email

router = APIRouter()


@router.get('/{node:int}/sendtext/', name='sendtext')
async def sendtext(request: Request, node: int, ctx: NodeContext = Depends(get_node_context)):
    app = request.app
    page = dict(
        node=node,
        url_slack=url_for(app, 'sendtextapi', opt='slack', channel_chatid_subject=None, text='some-text'),
        url_telegram=url_for(app, 'sendtextapi', opt='telegram', channel_chatid_subject=None, text='some-text'),
        url_email=url_for(app, 'sendtextapi', opt='email', channel_chatid_subject=None, text='some-text'),
    )
    return render(request, 'scrapydweb/send_text.html', node, ctx, page=page)


def _email_kwargs(s):
    g = s.get
    sender = g('EMAIL_SENDER', '')
    return dict(
        email_username=g('EMAIL_USERNAME', '') or sender,
        email_password=g('EMAIL_PASSWORD', ''),
        email_sender=sender,
        email_recipients=g('EMAIL_RECIPIENTS', []),
        smtp_server=g('SMTP_SERVER', ''),
        smtp_port=g('SMTP_PORT', 0),
        smtp_over_ssl=g('SMTP_OVER_SSL', False),
        smtp_connection_timeout=g('SMTP_CONNECTION_TIMEOUT', 30),
        subject='subject', content='content',
    )


async def _read_form(request):
    if 'application/json' in request.headers.get('content-type', ''):
        try:
            return await request.json()
        except Exception:
            return {}
    try:
        return dict(await request.form())
    except Exception:
        return {}


async def _sendtextapi(request, opt, channel_chatid_subject, text):
    app = request.app
    s = app.state.settings
    opt = 'telegram' if opt == 'tg' else opt
    form = await _read_form(request)
    qp = request.query_params
    email_kwargs = _email_kwargs(s)

    if opt == 'email':
        ccs = (channel_chatid_subject or qp.get('subject')
               or form.get('subject', s.get('EMAIL_SUBJECT', '') or 'Email from #scrapydweb'))
        recipients = re.findall(r'[^\s"\',;\[\]]+@[^\s"\',;\[\]]+',
                                qp.get('recipients', '') or str(form.get('recipients', '')))
        email_kwargs['email_recipients'] = recipients or s.get('EMAIL_RECIPIENTS', [])
    elif opt == 'slack':
        ccs = channel_chatid_subject or qp.get('channel') or form.get('channel', s.get('SLACK_CHANNEL', '') or 'general')
    else:
        ccs = channel_chatid_subject or qp.get('chat_id') or form.get('chat_id', s.get('TELEGRAM_CHAT_ID', 0))

    text = text or qp.get('text') or (json_dumps(form) if form else 'test')

    js = {}
    if opt == 'email':
        if not s.get('EMAIL_PASSWORD', ''):
            js = dict(status=ERROR, result="The EMAIL_PASSWORD option is unset")
        else:
            email_kwargs['subject'] = ccs
            email_kwargs['content'] = text
            result, reason = await run_in_threadpool(send_email, to_retry=True, **email_kwargs)
            if result is True:
                js = dict(status=OK, result=dict(reason=reason, sender=email_kwargs['email_sender'],
                                                 recipients=email_kwargs['email_recipients'],
                                                 subject=ccs, text=text))
            else:
                js = dict(status=ERROR, result=dict(reason=reason), debug=email_kwargs)
    elif opt == 'slack':
        token = s.get('SLACK_TOKEN', '')
        if not token:
            js = dict(status=ERROR, result="The SLACK_TOKEN option is unset")
        else:
            url = 'https://slack.com/api/chat.postMessage'
            data = dict(token=token, channel=ccs, text=text)
            status_code, r = await request_scrapyd(app.state.http_client, url, data=data, as_json=True)
            for key in ['auth', 'status', 'status_code', 'url', 'when']:
                r.pop(key, None)
            js = dict(url=url, status_code=status_code, result=r)
            js['status'] = OK if r.get('ok', False) else ERROR
            if js['status'] == ERROR:
                js['debug'] = dict(token=token, channel=ccs, text=text)
    else:  # telegram
        token = s.get('TELEGRAM_TOKEN', '')
        if not token:
            js = dict(status=ERROR, result="The TELEGRAM_TOKEN option is unset")
        else:
            url = 'https://api.telegram.org/bot%s/sendMessage' % token
            data = dict(text=text, chat_id=ccs)
            status_code, r = await request_scrapyd(app.state.http_client, url, data=data, as_json=True)
            for key in ['auth', 'status', 'status_code', 'url', 'when']:
                r.pop(key, None)
            js = dict(url=url, status_code=status_code, result=r)
            js['status'] = OK if r.get('ok', False) else ERROR
            if js['status'] == ERROR:
                js['debug'] = dict(token=token, chat_id=ccs, text=text)
    js['when'] = get_now_string(True)
    return JSONResponse(js)


def _make(opt):
    async def handler(request: Request, channel_chatid_subject: str = None, text: str = None):
        return await _sendtextapi(request, opt, channel_chatid_subject, text)
    return handler


for _opt in ('slack', 'telegram', 'tg', 'email'):
    for _suffix in ('/{channel_chatid_subject}/{text}', '/{text}', ''):
        router.add_api_route('/%s%s' % (_opt, _suffix), _make(_opt),
                             methods=['GET', 'POST'], name='sendtextapi')
