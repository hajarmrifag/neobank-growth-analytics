from uuid import uuid4


class BankingError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        self.message = message


class BankingService:
    """Business operations; each mutation commits as one database transaction."""

    def __init__(self, conn, session_id=None):
        self.conn = conn
        self.session_id = session_id

    def session_lock(self):
        if self.session_id:
            row = self.conn.execute(
                'SELECT id FROM banking.demo_sessions WHERE id = %s AND expires_at > clock_timestamp() FOR UPDATE',
                (self.session_id,),
            ).fetchone()
            if not row:
                raise BankingError(401, 'session_expired', 'Start a new demo session')

    def create_account(self, request):
        with self.conn.transaction():
            self.session_lock()
            if self.session_id:
                count = self.conn.execute('SELECT count(*) AS n FROM banking.accounts WHERE demo_session_id = %s', (self.session_id,)).fetchone()['n']
                if count >= 5:
                    raise BankingError(429, 'account_limit', 'Demo limit: five accounts per session')
            return self.conn.execute(
                '''INSERT INTO banking.accounts
                   (id, owner_name, currency, opening_balance_minor, balance_minor, demo_session_id)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING *''',
                (uuid4(), request.owner_name, request.currency,
                 request.opening_balance_minor, request.opening_balance_minor, self.session_id),
            ).fetchone()

    def account(self, account_id):
        row = self.conn.execute(
            'SELECT * FROM banking.accounts WHERE id = %s', (account_id,),
        ).fetchone()
        if row is None or row['demo_session_id'] != self.session_id:
            raise BankingError(404, 'account_not_found', 'Account not found')
        return row

    def transfer(self, request, key):
        if self.session_id:
            from hashlib import sha256
            key = sha256(f'{self.session_id}:{key}'.encode()).hexdigest()
        with self.conn.transaction():
            self.session_lock()
            # Serialize matching keys across processes, including first-ever requests.
            # Hash collisions only serialize unrelated requests; keys remain unique in SQL.
            self.conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (key,))
            previous = self.conn.execute(
                'SELECT * FROM banking.transfers WHERE idempotency_key = %s', (key,),
            ).fetchone()
            if previous:
                fields = ('source_account_id', 'destination_account_id', 'amount_minor', 'currency')
                if any(previous[field] != getattr(request, field) for field in fields):
                    raise BankingError(409, 'idempotency_conflict', 'Key already used for a different transfer')
                return previous, True

            if self.session_id:
                count = self.conn.execute('''SELECT count(*) AS n FROM banking.transfers t
                    JOIN banking.accounts a ON a.id = t.source_account_id WHERE a.demo_session_id = %s''', (self.session_id,)).fetchone()['n']
                if count >= 100:
                    raise BankingError(429, 'transfer_limit', 'Demo limit: 100 transfers per session')

            # Always acquire both row locks in UUID order to avoid opposite-transfer deadlocks.
            locked = self.conn.execute(
                '''SELECT * FROM banking.accounts WHERE id IN (%s, %s)
                   ORDER BY id FOR UPDATE''',
                (request.source_account_id, request.destination_account_id),
            ).fetchall()
            if len(locked) != 2 or any(row['demo_session_id'] != self.session_id for row in locked):
                raise BankingError(404, 'account_not_found', 'Source or destination account not found')
            accounts = {row['id']: row for row in locked}
            source = accounts[request.source_account_id]
            destination = accounts[request.destination_account_id]
            if source['balance_minor'] < request.amount_minor:
                raise BankingError(409, 'insufficient_funds', 'Insufficient funds')
            if destination['balance_minor'] + request.amount_minor > 9_000_000_000_000_000:
                raise BankingError(409, 'balance_limit', 'Destination balance limit exceeded')
            self.conn.execute(
                'UPDATE banking.accounts SET balance_minor = balance_minor - %s WHERE id = %s',
                (request.amount_minor, request.source_account_id),
            )
            self.conn.execute(
                'UPDATE banking.accounts SET balance_minor = balance_minor + %s WHERE id = %s',
                (request.amount_minor, request.destination_account_id),
            )
            result = self.conn.execute(
                '''INSERT INTO banking.transfers
                   (id, idempotency_key, source_account_id, destination_account_id, amount_minor, currency)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING *''',
                (uuid4(), key, request.source_account_id, request.destination_account_id,
                 request.amount_minor, request.currency),
            ).fetchone()
        return result, False

    def history(self, account_id, limit, offset):
        self.account(account_id)
        rows = self.conn.execute(
            '''SELECT *, CASE WHEN source_account_id = %s THEN 'outgoing' ELSE 'incoming' END AS direction
               FROM banking.transfers
               WHERE source_account_id = %s OR destination_account_id = %s
               ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s''',
            (account_id, account_id, account_id, limit, offset),
        ).fetchall()
        return {'items': rows, 'limit': limit, 'offset': offset}
