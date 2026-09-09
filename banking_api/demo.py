"""Run a small HTTP demo; creates two synthetic accounts on each invocation."""
import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    base = os.environ.get('BANKING_API_URL', 'http://127.0.0.1:8000').rstrip('/')
    token = None

    def request(path, payload=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if key:
            headers['Idempotency-Key'] = key
        data = json.dumps(payload).encode() if payload is not None else None
        with urlopen(Request(base + path, data=data, headers=headers), timeout=15) as response:
            return response.status, json.load(response)

    _, spec = request('/openapi.json')
    if '/demo/sessions' in spec['paths']:
        _, session = request('/demo/sessions', {})
        token = session['token']
    _, alice = request('/accounts', {'owner_name': 'Alice Demo', 'opening_balance_minor': 10000})
    _, bob = request('/accounts', {'owner_name': 'Bob Demo'})
    payload = {'source_account_id': alice['id'], 'destination_account_id': bob['id'], 'amount_minor': 2500}
    key = 'demo-' + str(uuid4())
    status, transaction = request('/transfers', payload, key)
    replay_status, replay = request('/transfers', payload, key)
    _, alice = request('/accounts/' + alice['id'])
    _, bob = request('/accounts/' + bob['id'])
    _, history = request('/accounts/' + alice['id'] + '/transactions')
    assert status == 201 and replay_status == 200 and transaction == replay
    assert alice['balance_minor'] == 7500 and bob['balance_minor'] == 2500
    assert len(history['items']) == 1
    print(json.dumps({'transfer': transaction, 'replay_status': replay_status,
                      'alice_balance_minor': alice['balance_minor'],
                      'bob_balance_minor': bob['balance_minor'],
                      'alice_history_count': len(history['items'])}, indent=2))


if __name__ == '__main__':
    main()
