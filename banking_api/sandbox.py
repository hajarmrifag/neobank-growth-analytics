"""Bounded, expiring anonymous sessions for the public portfolio demo."""
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

from banking_api.service import BankingError


def cleanup(conn):
    with conn.transaction():
        expired = conn.execute('''SELECT id FROM banking.demo_sessions
            WHERE expires_at <= clock_timestamp() ORDER BY id FOR UPDATE SKIP LOCKED''').fetchall()
        ids = [row['id'] for row in expired]
        if not ids:
            return
        conn.execute('''DELETE FROM banking.transfers WHERE source_account_id IN
            (SELECT id FROM banking.accounts WHERE demo_session_id = ANY(%s))''', (ids,))
        conn.execute('DELETE FROM banking.accounts WHERE demo_session_id = ANY(%s)', (ids,))
        conn.execute('DELETE FROM banking.demo_sessions WHERE id = ANY(%s)', (ids,))


def start_session(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('demo-session-creation', 0))")
        cleanup(conn)
        counts = conn.execute('''SELECT count(*) AS total,
            count(*) FILTER (WHERE created_at > clock_timestamp() - INTERVAL '1 minute') AS recent
            FROM banking.demo_sessions''').fetchone()
        if counts['total'] >= 200 or counts['recent'] >= 20:
            raise BankingError(429, 'demo_busy', 'Demo is busy; please try again in a minute')
        token = token_urlsafe(32)
        row = conn.execute('''INSERT INTO banking.demo_sessions (id, token_hash)
            VALUES (%s, %s) RETURNING expires_at''', (uuid4(), sha256(token.encode()).hexdigest())).fetchone()
    return {'token': token, 'expires_at': row['expires_at'], 'expires_in_seconds': 1800}


def authenticate(conn, token):
    if not token or len(token) > 128:
        raise BankingError(401, 'session_required', 'Create a demo session and use its token as a Bearer token')
    with conn.transaction():
        row = conn.execute('''SELECT *, window_start <= clock_timestamp() - INTERVAL '1 minute' AS new_window
            FROM banking.demo_sessions WHERE token_hash = %s AND expires_at > clock_timestamp() FOR UPDATE''',
            (sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:
            raise BankingError(401, 'session_expired', 'Invalid or expired demo session; start a new session')
        if row['new_window']:
            conn.execute('UPDATE banking.demo_sessions SET window_start = clock_timestamp(), request_count = 1 WHERE id = %s', (row['id'],))
        elif row['request_count'] >= 60:
            raise BankingError(429, 'rate_limit', 'Demo limit: 60 requests per minute')
        else:
            conn.execute('UPDATE banking.demo_sessions SET request_count = request_count + 1 WHERE id = %s', (row['id'],))
    return row['id']


class BodyLimitMiddleware:
    def __init__(self, app, maximum=4096):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(data) + len(chunk) > self.maximum:
                from starlette.responses import JSONResponse
                return await JSONResponse({'error': {'code': 'body_too_large', 'message': 'Maximum request body is 4 KB'}}, status_code=413)(scope, receive, send)
            data.extend(chunk)
            if not message.get('more_body', False):
                break
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
            return await receive()
        return await self.app(scope, replay, send)
