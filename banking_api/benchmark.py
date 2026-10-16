"""Compare history query plans using disposable temporary data only."""

import json
import os
import platform
from datetime import UTC, datetime
from statistics import median, stdev

from banking_api.db import connect


def main():
    with connect() as conn:
        conn.execute("SET LOCAL statement_timeout = 60000")
        conn.execute("""CREATE TEMP TABLE benchmark_transfers AS
            SELECT md5(i::text)::uuid AS id,
                   md5((i % 1000)::text)::uuid AS source_account_id,
                   md5(((i + 1) % 1000)::text)::uuid AS destination_account_id,
                   100::bigint AS amount_minor, 'GBP'::text AS currency,
                   TIMESTAMPTZ '2026-01-01' + i * INTERVAL '1 second' AS created_at
            FROM generate_series(1, 200000) AS i""")
        conn.execute("ANALYZE benchmark_transfers")
        query = """EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT *, CASE WHEN source_account_id = md5('42')::uuid
                           THEN 'outgoing' ELSE 'incoming' END AS direction
            FROM benchmark_transfers
            WHERE source_account_id = md5('42')::uuid OR destination_account_id = md5('42')::uuid
            ORDER BY created_at DESC, id DESC LIMIT 20 OFFSET 0"""

        result_query = query.replace("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)", "", 1)
        expected = conn.execute(result_query).fetchall()

        def measure():
            # First execution warms the cache; report median of the next five runs.
            conn.execute(query).fetchone()
            plans = [conn.execute(query).fetchone()["QUERY PLAN"][0] for _ in range(5)]
            return {
                "median_execution_ms": median(p["Execution Time"] for p in plans),
                "execution_samples_ms": [p["Execution Time"] for p in plans],
                "sample_stdev_ms": stdev(p["Execution Time"] for p in plans),
                "planning_samples_ms": [p["Planning Time"] for p in plans],
                "explain_plans": plans,
                "sample_plan": plans[-1],
            }

        before = measure()
        conn.execute(
            "CREATE INDEX ON benchmark_transfers (source_account_id, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX ON benchmark_transfers (destination_account_id, created_at DESC, id DESC)"
        )
        conn.execute("ANALYZE benchmark_transfers")
        after = measure()
        if conn.execute(result_query).fetchall() != expected:
            raise AssertionError("indexing changed ordered query results")
        print(
            json.dumps(
                {
                    "recorded_at_utc": datetime.now(UTC).isoformat(),
                    "client_platform": platform.platform(),
                    "server_cpu_label": os.environ.get("BANKING_BENCHMARK_CPU", "not recorded"),
                    "server_settings": {
                        name: conn.execute("SHOW " + name).fetchone()[name]
                        for name in ("shared_buffers", "work_mem", "jit")
                    },
                    "ordered_results_equal": True,
                    "result_rows": len(expected),
                    "rows": 200000,
                    "accounts": 1000,
                    "runs_per_case": 5,
                    "postgres_version": conn.execute("SHOW server_version").fetchone()[
                        "server_version"
                    ],
                    "before_indexes": before,
                    "after_indexes": after,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
