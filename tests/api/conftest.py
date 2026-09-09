import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from banking_api.db import initialize
from banking_api.main import create_app


@pytest.fixture(scope='session')
def database_url():
    """Create/drop only a uniquely named test database; never truncate demo data."""
    admin_url = os.environ.get('BANKING_TEST_ADMIN_URL')
    if not admin_url:
        pytest.fail('Set BANKING_TEST_ADMIN_URL to PostgreSQL with CREATEDB permission')
    name = 'banking_test_' + uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    params = conninfo_to_dict(admin_url)
    params['dbname'] = name
    url = make_conninfo(**params)
    try:
        initialize(url)
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as client:
        yield client
