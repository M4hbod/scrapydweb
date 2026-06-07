# coding: utf-8
"""Deploy -> schedule -> jobs -> log lifecycle against the live scrapyd."""
import os
import time

from tests.utils import cst

PROJECT = cst.PROJECT
VERSION = cst.VERSION
SPIDER = cst.SPIDER


def _deploy_egg(client, version=VERSION):
    egg = os.path.join(cst.ROOT_DIR, 'data', '%s.egg' % PROJECT)
    with open(egg, 'rb') as f:
        r = client.post('/1/deploy/upload/',
                        data={'project': PROJECT, 'version': version},
                        files={'file': ('%s.egg' % PROJECT, f.read())})
    return r.json()


def test_deploy_egg_upload(client):
    js = _deploy_egg(client)
    assert js['status'] == cst.OK, js
    assert js['project'] == PROJECT
    assert js['version'] == VERSION
    assert js['js']['spiders'] >= 1


def test_deploy_folders_listing(client):
    js = client.get('/api/1/deploy/folders/').json()
    assert js['status'] == cst.OK
    assert any(f['project'] == PROJECT for f in js['folders']), js['folders']


def test_deploy_folder_build(client):
    js = client.get('/api/1/deploy/folders/').json()
    folder = next(f['folder'] for f in js['folders'] if f['project'] == PROJECT and '-' not in f['folder'])
    r = client.post('/1/deploy/upload/', data={'project': PROJECT, 'version': VERSION + '-folder',
                                               'folder': folder})
    js = r.json()
    assert js['status'] == cst.OK, js


def test_deploy_bad_folder(client):
    js = client.post('/1/deploy/upload/', data={'project': 'x', 'version': 'v',
                                                'folder': 'no-such-folder'}).json()
    assert js['status'] == cst.ERROR
    assert 'scrapy.cfg not found' in js['text']


def test_listprojects_listspiders(client):
    js = client.get('/1/api/listprojects/').json()
    assert PROJECT in js['projects']
    js = client.get('/1/api/listversions/%s/' % PROJECT).json()
    assert VERSION in js['versions']
    js = client.get('/1/api/listspiders/%s/%s/' % (PROJECT, VERSION)).json()
    assert SPIDER in js['spiders']


def test_schedule_check_and_run(app, client):
    jobid = 'apitest_%s' % int(time.time())
    js = client.post('/1/schedule/check/', data=dict(
        project=PROJECT, _version=cst.DEFAULT_LATEST_VERSION, spider=SPIDER, jobid=jobid,
        additional='-d setting=CLOSESPIDER_TIMEOUT=20 -d arg1=val1')).json()
    assert js['filename'].endswith('.pickle')
    assert 'curl' in js['cmd'] and jobid in js['cmd']

    js = client.post('/1/schedule/run/', data=dict(filename=js['filename'])).json()
    assert js['status'] == cst.OK, js
    assert js['jobid'] == jobid

    # the job must show up in the jobs JSON (and persist to the DB view)
    deadline = time.time() + 180  # httpbin can be slow; CLOSESPIDER_TIMEOUT only closes gracefully
    seen = finished = False
    while time.time() < deadline:
        jjs = client.get('/api/1/jobs/').json()
        assert jjs['status'] == cst.OK, jjs
        rows = [j for j in jjs['jobs'] if j['job'] == jobid]
        if rows:
            seen = True
            if rows[0]['status'] == '2':
                finished = True
                break
        time.sleep(3)
    assert seen, 'job never appeared in /api/1/jobs/'
    assert finished, 'job never finished'

    # job->code link: scheduled with the default version -> the actual latest
    # version was resolved and recorded at schedule time
    latest = client.get('/1/api/listversions/%s/' % PROJECT).json()['versions'][-1]
    row = next(j for j in client.get('/api/1/jobs/').json()['jobs'] if j['job'] == jobid)
    assert row['version'] == latest, row
    # the code viewer serves any version deployed through scrapydweb (the
    # resolved latest may predate this suite, so check the egg we deployed)
    js = client.get('/api/code/%s/%s/' % (PROJECT, VERSION)).json()
    assert js['status'] == cst.OK and js['files']

    # log text + stats JSON
    js = client.get('/api/1/log/utf8/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert js['finished'] is True
    assert js['version'] == latest  # the log page links the code viewer
    assert 'scrapy.core.engine' in js['text']

    js = client.get('/api/1/log/stats/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert 'log_categories' in js['stats']

    js = client.get('/1/log/report/%s/%s/%s/' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert 'log_categories' in js

    # central stats collector: parse this node's logs over HTTP, no daemons
    from scrapydweb.services import logstats
    parsed = logstats.collect_all(app.config)
    assert parsed >= 1

    jjs = client.get('/api/1/jobs/').json()
    row = next(j for j in jjs['jobs'] if j['job'] == jobid)
    assert row['pages'] is not None and row['items'] is not None
    assert row['finish_reason'] == 'finished'

    # stats page now serves the collected stats (logparser_valid via DB row)
    js = client.get('/api/1/log/stats/%s/%s/%s/?job_finished=True' % (PROJECT, SPIDER, jobid)).json()
    assert js['status'] == cst.OK
    assert js['logparser_valid'] is True
    assert js['stats']['pages'] is not None


def test_search_finds_job(client):
    js = client.get('/api/1/search/?q=apitest').json()
    assert any('apitest' in r['job'] for r in js['results'])


def test_stop_and_delversion_cleanup(client):
    # delete the extra folder-built version; keep VERSION for later runs
    js = client.post('/1/api/delversion/%s/%s/' % (PROJECT, VERSION + '-folder')).json()
    assert js['status'] == cst.OK, js
