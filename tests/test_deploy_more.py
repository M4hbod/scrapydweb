# coding: utf-8
"""Deploy edge paths: multinode form, xhr slot/disk fallback, addversion failure, zip build."""
import os
import time

from tests.utils import cst

PROJECT = cst.PROJECT


def _egg_bytes():
    with open(os.path.join(cst.ROOT_DIR, 'data', '%s.egg' % PROJECT), 'rb') as f:
        return f.read()


def test_deploy_multinode_partial(client, fake_scrapyd):
    version = 'multi-%s' % int(time.time())
    r = client.post('/1/deploy/upload/',
                    data={'project': PROJECT, 'version': version,
                          'checked_amount': '2', '1': 'on', '2': 'on'},
                    files={'file': ('%s.egg' % PROJECT, _egg_bytes())})
    js = r.json()
    assert js['status'] == cst.OK
    assert js['overall'] == 'partial'  # node 2 is the unreachable fake-domain
    by_node = {res['node']: res for res in js['results']}
    assert by_node[1]['status'] == cst.OK
    assert by_node[2]['status'] == cst.ERROR
    client.post('/1/api/delversion/%s/%s/' % (PROJECT, version))


def test_deploy_xhr_slot_and_disk(client, fake_scrapyd):
    version = 'xhr-%s' % int(time.time())
    r = client.post('/1/deploy/upload/',
                    data={'project': PROJECT, 'version': version},
                    files={'file': ('%s.egg' % PROJECT, _egg_bytes())})
    assert r.json()['status'] == cst.OK
    eggname = '%s_%s.egg' % (PROJECT, version)
    js = client.post('/1/deploy/xhr/%s/%s/%s/' % (eggname, PROJECT, version)).json()
    assert js['status'] == cst.OK  # slot hit
    from scrapydweb.services.deploy_utils import slot
    slot.egg.pop(eggname, None)
    js = client.post('/1/deploy/xhr/%s/%s/%s/' % (eggname, PROJECT, version)).json()
    assert js['status'] == cst.OK  # disk fallback (DEPLOY_PATH egg)
    client.post('/1/api/delversion/%s/%s/' % (PROJECT, version))


def test_deploy_addversion_500(client, fake_scrapyd):
    fake_scrapyd.state.fail_next['addversion'] = 1
    r = client.post('/1/deploy/upload/',
                    data={'project': PROJECT, 'version': 'fail-%s' % int(time.time())},
                    files={'file': ('%s.egg' % PROJECT, _egg_bytes())})
    js = r.json()
    assert js['status'] == cst.ERROR


def test_deploy_zip_upload_builds_egg(client, fake_scrapyd):
    version = 'zip-%s' % int(time.time())
    zip_path = os.path.join(cst.ROOT_DIR, 'data', 'demo_outer.zip')
    with open(zip_path, 'rb') as f:
        r = client.post('/1/deploy/upload/',
                        data={'project': 'demo_outer', 'version': version},
                        files={'file': ('demo_outer.zip', f.read())})
    js = r.json()
    assert js['status'] == cst.OK, js
    client.post('/1/api/delproject/demo_outer/')
