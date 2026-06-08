# coding: utf-8
"""Live timer-task fire: real spider run via APScheduler (slow; `live` marker)."""
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



def test_task_fire_records_result(client):
    task_id = _add_task(client, action='add_fire', name='api-task-fire')
    deadline = time.time() + 60
    results = []
    while time.time() < deadline:
        js = client.get('/api/1/tasks/%s/results/' % task_id).json()
        # the executor commits the TaskResult row before its per-node
        # TaskJobResult rows -- only stop once the job results landed too
        if js['status'] == cst.OK and js['results'] and js['results'][0]['job_results']:
            results = js['results']
            break
        time.sleep(3)
    assert results, 'task never produced a result with job results'
    job_results = results[0]['job_results']
    assert job_results
    # node 1 is live; the multinode selection defaults to node 1 only
    assert any(r['status'] == cst.OK for r in job_results), job_results

    t = _find_task(client, task_id)
    assert t['run_times'] >= 1
    assert t['prev_run_result'] != cst.NA

    # the timer-task path records the job's version too (job->code link)
    jobid = next(r['result'] for r in job_results if r['status'] == cst.OK)
    deadline = time.time() + 60
    row = None
    while time.time() < deadline:
        rows = [j for j in client.get('/api/1/jobs/').json().get('jobs', []) if j['job'] == jobid]
        if rows:
            row = rows[0]
            break
        time.sleep(3)
    assert row is not None, 'task job never appeared in /api/1/jobs/'
    assert row['version'], row  # resolved latest version recorded by the executor

    _xhr(client, 'remove', task_id)
    _xhr(client, 'delete', task_id)
