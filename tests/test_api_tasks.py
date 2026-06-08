# coding: utf-8
"""Timer task lifecycle via the JSON endpoints (schedule.check w/ trigger + tasks.xhr)."""
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _ensure_project(client):
    js = client.get('/1/api/listprojects/').json()
    if PROJECT not in js.get('projects', []):
        import os
        egg = os.path.join(cst.ROOT_DIR, 'data', '%s.egg' % PROJECT)
        with open(egg, 'rb') as f:
            client.post('/1/deploy/upload/', data={'project': PROJECT, 'version': cst.VERSION},
                        files={'file': ('%s.egg' % PROJECT, f.read())})


def _add_task(client, action='add', name='api-task'):
    _ensure_project(client)
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER,
        jobid='task_api_%s' % int(time.time()),
        trigger='cron', action=action, name=name,
        year='*', month='*', day='*', week='*', day_of_week='*',
        hour='*', minute='*', second='*/30')).json()
    assert js['filename']
    js = client.post('/1/schedule/run/', data=dict(filename=js['filename'])).json()
    assert js['status'] == cst.OK, js
    assert js['task_id']
    return js['task_id']


def _find_task(client, task_id):
    js = client.get('/api/1/tasks/').json()
    assert js['status'] == cst.OK
    return next((t for t in js['tasks'] if t['id'] == task_id), None)


def _xhr(client, action, task_id=None):
    url = '/1/tasks/xhr/%s/' % action if task_id is None else '/1/tasks/xhr/%s/%s/' % (action, task_id)
    return client.post(url).json()


def test_task_add_pause_resume_remove(client):
    task_id = _add_task(client, action='add', name='api-task-cycle')
    t = _find_task(client, task_id)
    assert t is not None
    assert t['status'] == 'Running'
    assert t['name'] == 'api-task-cycle'
    assert t['next_run_time']

    js = _xhr(client, 'pause', task_id)
    assert js['status'] == cst.OK, js
    assert _find_task(client, task_id)['status'] == 'Paused'

    js = _xhr(client, 'resume', task_id)
    assert js['status'] == cst.OK, js
    assert _find_task(client, task_id)['status'] == 'Running'

    js = _xhr(client, 'remove', task_id)
    assert js['status'] == cst.OK, js
    assert _find_task(client, task_id)['status'] == 'Finished'

    js = _xhr(client, 'delete', task_id)
    assert js['status'] == cst.OK, js
    assert _find_task(client, task_id) is None


def test_task_results_404(client):
    r = client.get('/api/1/tasks/987654321/results/')
    assert r.status_code == 404


def test_scheduler_disable_enable(client):
    js = _xhr(client, 'disable')
    assert js['status'] == cst.OK, js
    assert client.get('/api/1/tasks/').json()['scheduler_enabled'] is False

    js = _xhr(client, 'enable')
    assert js['status'] == cst.OK, js
    assert client.get('/api/1/tasks/').json()['scheduler_enabled'] is True


def test_task_edit_via_replace_existing(client):
    task_id = _add_task(client, action='add', name='api-task-edit')
    # re-check with task_id + replace_existing to update in place
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER,
        jobid='task_api_edit', trigger='cron', action='add', name='api-task-edited',
        task_id=str(task_id), replace_existing='True',
        year='*', month='*', day='*', week='*', day_of_week='*',
        hour='*', minute='30', second='0')).json()
    js = client.post('/1/schedule/run/', data=dict(filename=js['filename'])).json()
    assert js['status'] == cst.OK, js
    assert js['task_id'] == task_id

    t = _find_task(client, task_id)
    assert t['name'] == 'api-task-edited'
    assert t['minute'] == '30'

    _xhr(client, 'remove', task_id)
    _xhr(client, 'delete', task_id)
