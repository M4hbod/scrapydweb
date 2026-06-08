# coding: utf-8
"""Fast timer-task execution against the fake scrapyd (0.2s polls, no spider waits)."""
import os
import time

from tests.utils import cst

PROJECT = cst.PROJECT
SPIDER = cst.SPIDER


def _ensure_project(client):
    js = client.get('/1/api/listprojects/').json()
    if PROJECT not in js.get('projects', []):
        egg = os.path.join(cst.ROOT_DIR, 'data', '%s.egg' % PROJECT)
        with open(egg, 'rb') as f:
            client.post('/1/deploy/upload/', data={'project': PROJECT, 'version': cst.VERSION},
                        files={'file': ('%s.egg' % PROJECT, f.read())})


def _add_task(client, action='add_fire', name='fast-task'):
    _ensure_project(client)
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER,
        jobid='fast_task_%s' % int(time.time()),
        trigger='cron', action=action, name=name,
        year='*', month='*', day='*', week='*', day_of_week='*',
        hour='*', minute='*', second='*/30')).json()
    js = client.post('/1/schedule/run/', data=dict(filename=js['filename'])).json()
    assert js['status'] == cst.OK, js
    return js['task_id']


def _xhr(client, action, task_id=None):
    url = '/1/tasks/xhr/%s/' % action if task_id is None else '/1/tasks/xhr/%s/%s/' % (action, task_id)
    return client.post(url).json()


def _wait_results(client, task_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        js = client.get('/api/1/tasks/%s/results/' % task_id).json()
        if js.get('status') == cst.OK and js['results'] and js['results'][0]['job_results']:
            return js['results']
        time.sleep(0.2)
    raise AssertionError('task produced no job results within %ss' % timeout)


def test_task_fire_fast(client, fake_scrapyd):
    task_id = _add_task(client)
    try:
        results = _wait_results(client, task_id)
        job_results = results[0]['job_results']
        assert any(r['status'] == cst.OK and r['node'] == 1 for r in job_results), job_results
        # executor resolved + recorded the job version (sync twins, via the fake)
        jobid = next(r['result'] for r in job_results if r['status'] == cst.OK)
        deadline = time.time() + 10
        row = None
        while time.time() < deadline:
            rows = [j for j in client.get('/api/1/jobs/').json().get('jobs', []) if j['job'] == jobid]
            if rows:
                row = rows[0]
                break
            time.sleep(0.2)
        assert row is not None
        assert row['version'] == cst.VERSION
    finally:
        _xhr(client, 'remove', task_id)
        _xhr(client, 'delete', task_id)


def test_task_dump_and_fire_xhr(client, fake_scrapyd):
    task_id = _add_task(client, action='add')
    try:
        js = _xhr(client, 'dump', task_id)
        assert js['status'] == cst.OK
        assert js['data']['id'] == task_id
        assert js['data']['apscheduler_job']['id'] == str(task_id)
        js = _xhr(client, 'fire', task_id)
        assert js['status'] == cst.OK
    finally:
        _xhr(client, 'remove', task_id)
        _xhr(client, 'delete', task_id)


def test_task_executor_multinode_fail_row(app, client, fake_scrapyd, monkeypatch):
    """Node 2 (fake-domain) fails -> TaskJobResult error row; node 1 passes."""
    import scrapydweb.services.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod.time, 'sleep', lambda *_: None)  # skip the 3s retry waits

    _ensure_project(client)
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER,
        jobid='fast_task_multi_%s' % int(time.time()),
        trigger='cron', action='add', name='fast-task-multi',
        year='*', month='*', day='*', week='*', day_of_week='*',
        hour='*', minute='*', second='*/30')).json()
    js = client.post('/1/schedule/run/', data={
        'filename': js['filename'], 'checked_amount': '2', '1': 'on', '2': 'on'}).json()
    task_id = js['task_id']
    try:
        from scrapydweb.services.tasks import execute_task
        execute_task(task_id)  # run synchronously, no scheduler wait
        js = client.get('/api/1/tasks/%s/results/' % task_id).json()
        result = js['results'][0]
        assert result['pass_count'] == 1 and result['fail_count'] == 1
        by_node = {r['node']: r for r in result['job_results']}
        assert by_node[1]['status'] == cst.OK
        assert by_node[2]['status'] != cst.OK
    finally:
        _xhr(client, 'remove', task_id)
        _xhr(client, 'delete', task_id)


def test_tasks_listing_fields(client, fake_scrapyd):
    task_id = _add_task(client, action='add', name='fast-task-fields')
    try:
        js = client.get('/api/1/tasks/').json()
        t = next(t for t in js['tasks'] if t['id'] == task_id)
        assert t['status'] == 'Running'
        assert t['next_run_time']
        assert t['project'] == PROJECT
    finally:
        _xhr(client, 'remove', task_id)
        _xhr(client, 'delete', task_id)


def test_schedule_task_rerun_and_missing(client, fake_scrapyd):
    task_id = _add_task(client, action='add', name='fast-task-rerun')
    try:
        js = client.post('/1/schedule/task/',
                         data={'task_id': str(task_id), 'jobid': 'rerun-%s' % task_id}).json()
        assert js['status'] == cst.OK
        # version recorded for the rerun job (source 'task')
        row = next(j for j in client.get('/api/1/jobs/').json()['jobs']
                   if j['job'] == 'rerun-%s' % task_id)
        assert row['version'] == cst.VERSION

        js = client.post('/1/schedule/task/',
                         data={'task_id': '987654321', 'jobid': 'nope'}).json()
        assert js['status'] == cst.ERROR
        assert 'not found' in js['message']
    finally:
        _xhr(client, 'remove', task_id)
        _xhr(client, 'delete', task_id)


def test_tasks_xhr_list_and_delete_result(client, fake_scrapyd):
    task_id = _add_task(client, action='add', name='fast-task-list')
    try:
        from scrapydweb.services.tasks import execute_task
        execute_task(task_id)
        js = _xhr(client, 'list')
        assert js['status'] == cst.OK and task_id in js['ids']
        results = client.get('/api/1/tasks/%s/results/' % task_id).json()['results']
        tr_id = results[0]['id']
        js = client.post('/1/tasks/xhr/delete/%s/%s/' % (task_id, tr_id)).json()
        assert js['status'] == cst.OK
        js = client.post('/1/tasks/xhr/delete/%s/%s/' % (task_id, tr_id)).json()
        assert js['status'] == cst.ERROR  # already gone
    finally:
        _xhr(client, 'remove', task_id)
        _xhr(client, 'delete', task_id)


def test_tasks_xhr_dump_missing_task(client):
    js = client.post('/1/tasks/xhr/dump/987654321/').json()
    assert js['status'] == cst.ERROR
