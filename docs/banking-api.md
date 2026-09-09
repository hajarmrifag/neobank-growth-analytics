# Banking transaction API

A local Python/FastAPI and PostgreSQL simulation extending the neobank analytics
portfolio with transactional backend engineering. Uses Python 3.12. The existing
dashboard continues to analyse its original synthetic dataset. API activity lives
in a dedicated database and is not automatically incorporated into those findings.

## Start

From the repository root, with Docker Desktop running:

```bash
python3 scripts/init-api-env.py
docker compose --env-file .env.api -f compose.api.yml up -d --build
```

Open http://localhost:8000/docs for interactive API documentation. PostgreSQL is
available on localhost:55432. Both published ports bind only to the local machine.
Data persists in a dedicated Docker volume. To stop the services, preserving data:

```bash
docker compose --env-file .env.api -f compose.api.yml stop
```

This is a **local demonstration with synthetic money**. The database credentials
are generated into ignored `.env.api` by the setup script. There is no authentication, account
ownership enforcement, real payment rail, or production accounting ledger. Do not
expose this service publicly or use it for real customer data or money.

## Try a transfer

For an automatic example that creates two synthetic accounts, transfers £25,
retries the request and verifies balances/history:

```bash
docker compose --env-file .env.api -f compose.api.yml exec banking-api python -m banking_api.demo
```

In `/docs`, execute `POST /accounts` twice:

```json
{"owner_name":"Alice Demo","opening_balance_minor":10000,"currency":"GBP"}
```

```json
{"owner_name":"Bob Demo","opening_balance_minor":0,"currency":"GBP"}
```

Copy their returned `id` values into `POST /transfers`, using `demo-transfer-001`
as the required `Idempotency-Key` header:

```json
{
  "source_account_id": "<Alice's UUID>",
  "destination_account_id": "<Bob's UUID>",
  "amount_minor": 2500,
  "currency": "GBP"
}
```

Alice now has 7500 pence (£75); Bob has 2500 pence (£25). Submit the same transfer
with the same key again: the API returns the original transfer with HTTP 200 and
`Idempotency-Replayed: true`, without moving money again. A new key requests a new
transfer. Changing the payload with a used key returns HTTP 409.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Check database/schema connectivity |
| `POST /accounts` | Create an account with optional synthetic opening funds |
| `GET /accounts/{id}` | Retrieve account details and current balance |
| `POST /transfers` | Transfer GBP between two accounts |
| `GET /accounts/{id}/transactions?limit=20&offset=0` | Newest transfers first, with direction |

Amounts are **integer pence**, not decimal pounds. Negative amounts, floats,
booleans, numeric strings, unsupported currencies and unknown fields are rejected.
Opening funds and individual transfers are capped at 1,000,000,000,000 pence.
Balances cannot be negative or exceed 9,000,000,000,000,000 pence.

## Design and guarantees

- `models.py`: request validation and explicit response models.
- `main.py`: HTTP routes, error responses, request IDs and timing logs. Logs omit
  request bodies and use route templates rather than account IDs.
- `service.py`: a `BankingService` class owns business rules and SQL transactions.
- `db.py` / `schema.sql`: connections, initial schema and database constraints.

One PostgreSQL transaction encloses debit, credit and transfer insertion. Failure
rolls all three back. Both account rows are locked in UUID order before checking
the balance, so concurrent requests cannot spend the same funds or deadlock merely
by transferring in opposite directions. This uses PostgreSQL's default READ
COMMITTED isolation and explicit row locks.

A transaction-scoped advisory lock serializes requests for the same idempotency
key before checking persisted transfers. The key also has a unique database
constraint. Successful keys persist with their original transfer; failed attempts
roll back and do not reserve a key. Clients should retry a timeout or uncertain
response with **the same key**, since a commit may already have happened.
Keys are global in this single-tenant demo. Account creation is not idempotent.

History is a transfer journal, not a complete double-entry general ledger.
Opening funds are recorded on the account separately. History uses bounded offset
pagination; new transfers between page requests can shift later pages. A production
extension would use cursor pagination, authentication/authorization, database roles
with limited privileges, reconciliation and versioned migrations.

## Run tests

The test runner creates a uniquely named database, then drops only that test
database. The configured PostgreSQL role must have CREATEDB permission.
Tests do not truncate the demo or analytics tables.

```bash
python3.12 -m venv .venv-api
.venv-api/bin/python -m pip install -r requirements-api-dev.txt
python3 scripts/init-api-env.py
set -a
source .env.api
set +a
docker compose --env-file .env.api -f compose.api.yml up -d banking-db
export BANKING_TEST_ADMIN_URL="postgresql://banking_demo:${BANKING_DEMO_PASSWORD}@127.0.0.1:55432/postgres"
.venv-api/bin/python -m pytest tests/api -q
```

Tests use real PostgreSQL. They cover insufficient funds, request validation,
history, idempotency replay/conflicts, concurrent duplicate requests, concurrent
overspending, opposite-direction transfers, and an injected database failure after
both balance updates to prove rollback. GitHub Actions runs them against PostgreSQL
16 when the repository is pushed.

For local Python development instead of the API container:

```bash
set -a
source .env.api
set +a
export BANKING_DATABASE_URL="postgresql://banking_demo:${BANKING_DEMO_PASSWORD}@127.0.0.1:55432/banking_demo"
.venv-api/bin/python -m banking_api.db
.venv-api/bin/uvicorn banking_api.main:app --reload
```

Stop the Compose API service first if it already occupies port 8000.

## Reproduce the index comparison

```bash
set -a
source .env.api
set +a
export BANKING_DATABASE_URL="postgresql://banking_demo:${BANKING_DEMO_PASSWORD}@127.0.0.1:55432/banking_demo"
.venv-api/bin/python -m banking_api.benchmark
```

The benchmark generates 200,000 transfers across 1,000 accounts in a disposable
temporary table. It compares the history query before/after the two account/history
indexes, reporting `EXPLAIN ANALYZE` plans and median database execution times across
five warmed runs. It does not alter application tables or indexes. This is a local
query experiment, not an HTTP throughput or production performance claim. Indexes
cost storage and extra work on writes; their benefit depends on data distribution.

Measured locally on 9 September 2026 with PostgreSQL 16.15 in Docker Desktop:

| History query, 200,000 synthetic transfers | Median database execution |
| --- | --- |
| Before account/history indexes | 6.321 ms |
| After account/history indexes | 0.108 ms |

See [saved plans and measurements](banking-api-benchmark.json). These measurements
cover one account and warmed temporary-table data; they exclude HTTP and network
latency and should not be generalized to end-to-end application performance.

## Interview walkthrough

1. Show the transfer and replay in `/docs`.
2. Explain integer money and why both updates must be atomic.
3. Walk through lock ordering and a concurrent overspending test.
4. Explain why a unique key alone does not provide complete retry semantics.
5. Show the forced-failure test and the before/after index plans.
6. Explain the simulation boundaries and the next engineering improvements.
