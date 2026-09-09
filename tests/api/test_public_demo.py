from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from banking_api.db import connect
from banking_api.main import create_app
from banking_api.sandbox import cleanup


def session(client):
    response = client.post('/demo/sessions')
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def account(client, headers):
    response = client.post('/accounts', headers=headers, json={'owner_name': 'Fictional Demo', 'opening_balance_minor': 1000})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_public_session_isolation_and_scoped_keys(database_url):
    with TestClient(create_app(database_url, public_demo=True)) as client:
        assert client.post('/accounts', json={'owner_name': 'Demo'}).status_code == 401
        a, b = session(client), session(client)
        a1, a2, b1, b2 = account(client, a), account(client, a), account(client, b), account(client, b)
        assert client.get(f'/accounts/{a1}', headers=b).status_code == 404
        assert client.get(f'/accounts/{a1}/transactions', headers=b).status_code == 404
        payload = {'source_account_id': a1, 'destination_account_id': b1, 'amount_minor': 100}
        assert client.post('/transfers', headers={**a, 'Idempotency-Key': 'same'}, json=payload).status_code == 404
        for headers, src, dst in [(a, a1, a2), (b, b1, b2)]:
            payload = {'source_account_id': src, 'destination_account_id': dst, 'amount_minor': 100}
            assert client.post('/transfers', headers={**headers, 'Idempotency-Key': 'same'}, json=payload).status_code == 201
            assert client.post('/transfers', headers={**headers, 'Idempotency-Key': 'same'}, json=payload).status_code == 200
        assert client.get('/health').status_code == 200
        assert client.get('/').status_code == 200


def test_public_limits(database_url):
    with TestClient(create_app(database_url, public_demo=True)) as client:
        headers = session(client)
        for _ in range(5):
            account(client, headers)
        assert client.post('/accounts', headers=headers, json={'owner_name': 'Demo'}).status_code == 429
        assert client.post('/accounts', headers=headers, content='x' * 5000).status_code == 413
        with connect(database_url) as conn:
            conn.execute('UPDATE banking.demo_sessions SET request_count = 60')
        assert client.get('/accounts/00000000-0000-0000-0000-000000000000', headers=headers).status_code == 429


def test_expiry_cleanup_preserves_local_accounts(database_url):
    with TestClient(create_app(database_url, public_demo=False)) as local:
        local_id = local.post('/accounts', json={'owner_name': 'Local Demo'}).json()['id']
    with TestClient(create_app(database_url, public_demo=True)) as client:
        headers = session(client)
        one, two = account(client, headers), account(client, headers)
        response = client.post('/transfers', headers={**headers, 'Idempotency-Key': 'expiry'}, json={
            'source_account_id': one, 'destination_account_id': two, 'amount_minor': 10})
        assert response.status_code == 201
        with connect(database_url) as conn:
            conn.execute("UPDATE banking.demo_sessions SET expires_at = clock_timestamp() - INTERVAL '1 second'")
        assert client.get(f'/accounts/{one}', headers=headers).status_code == 401
        with connect(database_url) as conn:
            cleanup(conn)
            assert conn.execute('SELECT count(*) AS n FROM banking.demo_sessions').fetchone()['n'] == 0
            assert conn.execute('SELECT id FROM banking.accounts WHERE id = %s', (one,)).fetchone() is None
            assert conn.execute('SELECT id FROM banking.accounts WHERE id = %s', (local_id,)).fetchone()


def test_concurrent_account_quota(database_url):
    app = create_app(database_url, public_demo=True)
    with TestClient(app) as client:
        headers = session(client)
        def create(_):
            return client.post('/accounts', headers=headers, json={'owner_name': 'Demo'}).status_code
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(create, range(8)))
        assert sorted(statuses) == [201] * 5 + [429] * 3
