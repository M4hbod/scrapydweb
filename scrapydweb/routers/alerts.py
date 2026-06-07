# coding: utf-8
"""Alert endpoints: channel test sends + per-project/spider rule CRUD."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..db import SessionLocal
from ..models import AlertRule
from ..services import notify
from ..services.alert_rules import rule_dict, validate_rule_payload

router = APIRouter(prefix='/api/alerts')


@router.post('/test', name='alerts.test')
async def test_alert(request: Request):
    body = await request.json()
    channel = str(body.get('channel') or '')
    if channel not in notify.CHANNELS:
        return JSONResponse({'status': 'error', 'message': 'unknown channel'}, status_code=400)
    settings = request.app.state.settings
    subject = '[scrapydweb] test alert'
    text = 'Test alert from scrapydweb -- your %s channel works.' % channel
    ok, result = await run_in_threadpool(notify.CHANNELS[channel], settings, subject, text)
    return JSONResponse({'status': 'ok' if ok else 'error', 'result': result})


# ------------------------------------------------------------------ rules CRUD
@router.get('/rules', name='alerts.rules')
async def rules_list():
    async with SessionLocal() as s:
        rows = (await s.execute(select(AlertRule).order_by(AlertRule.id))).scalars().all()
        return JSONResponse({'status': 'ok', 'rules': [rule_dict(r) for r in rows]})


@router.post('/rules', name='alerts.rules_create')
async def rules_create(request: Request):
    body = await request.json()
    fields, err = validate_rule_payload(body)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        rule = AlertRule(**fields)
        s.add(rule)
        await s.commit()
        return JSONResponse({'status': 'ok', 'rule': rule_dict(rule)})


@router.put('/rules/{rule_id:int}', name='alerts.rules_update')
async def rules_update(request: Request, rule_id: int):
    body = await request.json()
    fields, err = validate_rule_payload(body, partial=True)
    if err:
        return JSONResponse({'status': 'error', 'message': err}, status_code=400)
    async with SessionLocal() as s:
        rule = (await s.execute(select(AlertRule).filter_by(id=rule_id))).scalar_one_or_none()
        if rule is None:
            return JSONResponse({'status': 'error', 'message': 'rule not found'}, status_code=404)
        for k, v in fields.items():
            setattr(rule, k, v)
        await s.commit()
        return JSONResponse({'status': 'ok', 'rule': rule_dict(rule)})


@router.delete('/rules/{rule_id:int}', name='alerts.rules_delete')
async def rules_delete(rule_id: int):
    async with SessionLocal() as s:
        rule = (await s.execute(select(AlertRule).filter_by(id=rule_id))).scalar_one_or_none()
        if rule is None:
            return JSONResponse({'status': 'error', 'message': 'rule not found'}, status_code=404)
        await s.delete(rule)
        await s.commit()
    return JSONResponse({'status': 'ok'})


@router.post('/rules/preview', name='alerts.rules_preview')
async def rules_preview(request: Request):
    """Resolved effective alert settings for one (project, spider) -- 'which rule wins'."""
    from ..services.alert_rules import effective_settings, matching_rules
    from ..vars import ALERT_TRIGGER_KEYS
    body = await request.json()
    project = str(body.get('project') or '')
    spider = str(body.get('spider') or '')
    async with SessionLocal() as s:
        rows = (await s.execute(select(AlertRule).filter_by(enabled=True)
                                .order_by(AlertRule.id))).scalars().all()
        rules = [rule_dict(r) for r in rows]
    settings = request.app.state.settings
    eff = effective_settings(settings, rules, project, spider)
    keys = (['LOG_%s_THRESHOLD' % k for k in ALERT_TRIGGER_KEYS]
            + ['LOG_%s_TRIGGER_STOP' % k for k in ALERT_TRIGGER_KEYS]
            + ['LOG_%s_TRIGGER_FORCESTOP' % k for k in ALERT_TRIGGER_KEYS]
            + ['ON_JOB_FINISHED', 'ON_JOB_RUNNING_INTERVAL',
               'ENABLE_SLACK_ALERT', 'ENABLE_TELEGRAM_ALERT', 'ENABLE_EMAIL_ALERT'])
    return JSONResponse({'status': 'ok',
                         'matched_rule_ids': [r['id'] for r in matching_rules(rules, project, spider)],
                         'effective': {k: eff.get(k) for k in keys}})
