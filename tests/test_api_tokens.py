# coding: utf-8
"""Personal access tokens: minting, Bearer auth, revocation."""


def test_token_create_list_delete(client):
    r = client.post('/api/tokens', json={'name': 'curl-runner'}).json()
    assert r['status'] == 'ok'
    raw = r['plaintext']
    assert raw.startswith('sdw_')
    tid = r['token']['id']
    # listed, but never exposes the plaintext or hash
    lst = client.get('/api/tokens').json()['tokens']
    row = next(t for t in lst if t['id'] == tid)
    assert 'plaintext' not in row and 'token_hash' not in row
    assert row['prefix'].startswith('sdw_')
    # name is required
    assert client.post('/api/tokens', json={'name': ''}).json()['status'] == 'error'


def test_bearer_token_authenticates(client):
    raw = client.post('/api/tokens', json={'name': 'api'}).json()['plaintext']

    # drop the session cookie: now only the Bearer token can authenticate
    client.cookies.clear()
    auth = {'Authorization': 'Bearer %s' % raw}
    assert client.get('/api/groups').status_code == 401
    assert client.get('/api/groups', headers=auth).status_code == 200
    assert client.get('/api/groups',
                      headers={'Authorization': 'Bearer sdw_wrong'}).status_code == 401

    # revoke (via the token itself) -> it stops working
    tid = client.get('/api/tokens', headers=auth).json()['tokens'][0]['id']
    assert client.delete('/api/tokens/%s' % tid, headers=auth).status_code == 200
    assert client.get('/api/groups', headers=auth).status_code == 401
