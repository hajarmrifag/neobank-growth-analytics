# Transaction API engineering and verification

Local verification on 16 October 2026 used Python 3.12, the pinned requirements-dev.txt dependencies, and an isolated PostgreSQL 16.15 server. All **37 tests passed** across analytics and PostgreSQL-backed API tests; the API suite exercised concurrent spending, duplicate retries, opposite-direction transfers and injected-failure rollback. Ruff passed. One dependency deprecation warning remains. This is actual database execution, not an InMemory approximation.

The service's transaction boundary covers request-key serialization, ordered row locks, balance checks, debit, credit and transfer insertion. Returned outcomes are tied to committed requests; an external caller still needs to handle lost responses and retry with the same key/payload. This is a synthetic demonstration with no production authentication/ledger/settlement guarantees.

## Run tests against your own disposable server

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export BANKING_TEST_ADMIN_URL='postgresql://YOUR_TEST_USER:YOUR_TEST_PASSWORD@localhost:5432/postgres'
python -m pytest
ruff check .
```

The fixture creates a unique new database and drops only that database; it never truncates an existing application database. CI provisions PostgreSQL 16 and separately exercises the Docker demo over HTTP. Local testing does not substitute for a current Docker/remote-CI run.

## Query-plan measurement

[Raw run, 16 October 2026](banking-api-benchmark-2026-10-16.json): 200,000 synthetic transfers, 1,000 accounts; one warm-up and five measured EXPLAIN ANALYZE runs per condition. Median database execution was **12.909 ms before** and **0.153 ms after** indexes. The exact ordered result rows matched before/after. CPU: Apple M5, 16 GiB RAM, macOS 26.5; PostgreSQL 16.15 locally compiled with ICU/readline/zlib disabled. No external load or network/API latency is measured.

The raw file retains all five plans, execution/planning samples, sample standard deviation and server settings. Before always precedes index creation/after, so cache/time-order effects remain a limitation. Five warmed executions do not justify p99 or production-throughput claims. [Historical results](banking-api-benchmark.json) are preserved; this run does not rewrite the previous 6.321/0.108 ms observation. Index maintenance has write/storage costs.

```sh
export BANKING_DATABASE_URL='postgresql://YOUR_TEST_USER:YOUR_TEST_PASSWORD@localhost:5432/postgres'
BANKING_BENCHMARK_CPU='YOUR ACTUAL DATABASE SERVER CPU' python -m banking_api.benchmark > benchmark-run.json
```

The benchmark uses only a temporary table. Source changes should produce new dated evidence, not overwrite historical results.
