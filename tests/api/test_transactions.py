from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from banking_api.db import connect
from banking_api.main import create_app
from banking_api.models import TransferCreate
from banking_api.service import BankingService


def account(client, balance=0):
    result = client.post('/accounts', json={'owner_name': 'Demo Customer', 'opening_balance_minor': balance})
    assert result.status_code == 201, result.text
    return result.json()['id']


def body(source, destination, amount=100):
    return {'source_account_id': source, 'destination_account_id': destination, 'amount_minor': amount}


def transfer(client, payload, key=None):
    return client.post('/transfers', json=payload, headers={'Idempotency-Key': key or str(uuid4())})


def balance(client, account_id):
    return client.get(f'/accounts/{account_id}').json()['balance_minor']


def test_transfer_replay_conflict_and_history(client):
    source, destination = account(client, 1000), account(client)
    payload, key = body(source, destination, 250), str(uuid4())
    first = transfer(client, payload, key)
    assert first.status_code == 201
    assert first.headers['Idempotency-Replayed'] == 'false'
    replay = transfer(client, payload, key)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert replay.headers['Idempotency-Replayed'] == 'true'
    conflict = transfer(client, body(source, destination, 251), key)
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'idempotency_conflict'
    assert (balance(client, source), balance(client, destination)) == (750, 250)
    for account_id, direction in [(source, 'outgoing'), (destination, 'incoming')]:
        items = client.get(f'/accounts/{account_id}/transactions').json()['items']
        assert len(items) == 1
        assert items[0]['direction'] == direction
        assert items[0]['id'] == first.json()['id']


def test_insufficient_funds_and_missing_account_leave_balances_unchanged(client):
    source, destination = account(client, 100), account(client)
    response = transfer(client, body(source, destination, 101))
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'insufficient_funds'
    assert transfer(client, body(source, str(uuid4()), 50)).status_code == 404
    assert (balance(client, source), balance(client, destination)) == (100, 0)
    assert client.get(f'/accounts/{source}/transactions').json()['items'] == []


@pytest.mark.parametrize('amount', [0, -1, 1.5, '100', True, 1_000_000_000_001])
def test_invalid_amounts(client, amount):
    result = transfer(client, body(str(uuid4()), str(uuid4()), amount))
    assert result.status_code == 422


@pytest.mark.parametrize('payload', [
    {'owner_name': '  '}, {'owner_name': 'A', 'opening_balance_minor': -1},
    {'owner_name': 'A', 'opening_balance_minor': 0.5},
    {'owner_name': 'A', 'currency': 'USD'}, {'owner_name': 'A', 'admin': True},
])
def test_invalid_accounts(client, payload):
    assert client.post('/accounts', json=payload).status_code == 422


def test_request_validation_and_health(client):
    source = account(client)
    assert transfer(client, body(source, source)).status_code == 422
    payload = body(source, str(uuid4()))
    assert client.post('/transfers', json=payload).status_code == 422
    assert transfer(client, payload, ' ').status_code == 422
    assert transfer(client, dict(payload, currency='USD')).status_code == 422
    assert client.get('/accounts/not-a-uuid').status_code == 422
    assert client.get(f'/accounts/{uuid4()}').status_code == 404
    assert client.get(f'/accounts/{uuid4()}/transactions').status_code == 404
    assert client.get(f'/accounts/{source}/transactions?limit=101').status_code == 422
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/health').headers['X-Request-ID']


def test_history_pagination(client):
    source, destination = account(client, 1000), account(client)
    ids = [transfer(client, body(source, destination)).json()['id'] for _ in range(3)]
    page = client.get(f'/accounts/{source}/transactions?limit=2').json()
    assert [item['id'] for item in page['items']] == ids[::-1][:2]
    page = client.get(f'/accounts/{source}/transactions?limit=2&offset=2').json()
    assert [item['id'] for item in page['items']] == [ids[0]]


def concurrent_requests(database_url, payloads):
    barrier = Barrier(len(payloads))
    def run(item):
        with TestClient(create_app(database_url)) as client:
            barrier.wait(timeout=10)
            return transfer(client, *item)
    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        return list(pool.map(run, payloads))


def test_concurrent_spending_cannot_overdraw(client, database_url):
    source, destination = account(client, 1000), account(client)
    results = concurrent_requests(database_url, [(body(source, destination, 150), str(uuid4())) for _ in range(10)])
    assert sorted(r.status_code for r in results) == [201] * 6 + [409] * 4
    assert (balance(client, source), balance(client, destination)) == (100, 900)
    assert len(client.get(f'/accounts/{source}/transactions').json()['items']) == 6


def test_concurrent_same_key_moves_money_once(client, database_url):
    source, destination = account(client, 1000), account(client)
    payload, key = body(source, destination, 250), str(uuid4())
    results = concurrent_requests(database_url, [(payload, key)] * 8)
    assert sorted(r.status_code for r in results) == [200] * 7 + [201]
    assert len({r.json()['id'] for r in results}) == 1
    assert (balance(client, source), balance(client, destination)) == (750, 250)


def test_opposite_transfers_do_not_deadlock(client, database_url):
    a, b = account(client, 1000), account(client, 1000)
    results = concurrent_requests(database_url, [
        (body(a, b, 10) if i % 2 else body(b, a, 10), str(uuid4())) for i in range(10)
    ])
    assert all(r.status_code == 201 for r in results)
    assert (balance(client, a), balance(client, b)) == (1000, 1000)


def test_database_failure_after_updates_rolls_back_everything(client, database_url):
    source, destination = account(client, 1000), account(client)
    key = str(uuid4())
    # Inject a real PostgreSQL failure at the final INSERT, after both UPDATEs.
    with connect(database_url) as conn:
        conn.execute('''CREATE FUNCTION banking.fail_test_insert() RETURNS trigger AS $$
                        BEGIN RAISE EXCEPTION 'Injected insert failure'; END;
                        $$ LANGUAGE plpgsql''')
        conn.execute('''CREATE TRIGGER test_insert_failure BEFORE INSERT ON banking.transfers
                        FOR EACH ROW EXECUTE FUNCTION banking.fail_test_insert()''')
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            with connect(database_url) as conn:
                BankingService(conn).transfer(TransferCreate(**body(source, destination)), key)
        assert (balance(client, source), balance(client, destination)) == (1000, 0)
        assert client.get(f'/accounts/{source}/transactions').json()['items'] == []
    finally:
        with connect(database_url) as conn:
            conn.execute('DROP TRIGGER test_insert_failure ON banking.transfers')
            conn.execute('DROP FUNCTION banking.fail_test_insert()')
    # A rolled-back attempt does not reserve the key.
    assert transfer(client, body(source, destination), key).status_code == 201
