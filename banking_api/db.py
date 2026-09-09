import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def connect(database_url=None):
    url = database_url or os.environ.get('BANKING_DATABASE_URL')
    if not url:
        raise RuntimeError('Set BANKING_DATABASE_URL to a PostgreSQL connection URL')
    return psycopg.connect(
        url, row_factory=dict_row, connect_timeout=5,
        options='-c statement_timeout=10000 -c lock_timeout=5000',
    )


def initialize(database_url=None):
    with connect(database_url) as conn:
        conn.execute(Path(__file__).with_name('schema.sql').read_text())


if __name__ == '__main__':
    initialize()
    print('Banking schema initialized.')
