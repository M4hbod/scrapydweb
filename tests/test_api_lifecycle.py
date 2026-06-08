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




def test_stop_and_delversion_cleanup(client):
    # delete the extra folder-built version; keep VERSION for later runs
    js = client.post('/1/api/delversion/%s/%s/' % (PROJECT, VERSION + '-folder')).json()
    assert js['status'] == cst.OK, js
