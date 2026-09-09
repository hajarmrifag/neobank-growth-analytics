#!/bin/bash
set -euo pipefail
export PGDATA=/tmp/banking-demo-pg
mkdir -p /tmp/banking-demo-socket
chmod 700 /tmp/banking-demo-socket
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    initdb -D "$PGDATA" --auth-local=trust --auth-host=reject --no-locale >/dev/null
fi
pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -c unix_socket_directories='/tmp/banking-demo-socket' -c shared_buffers=32MB -c max_connections=40" -w start
api_pid=''
cleanup() {
    if [ -n "$api_pid" ]; then kill -TERM "$api_pid" 2>/dev/null || true; fi
    pg_ctl -D "$PGDATA" -m fast -w stop || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT
export BANKING_DATABASE_URL='postgresql:///postgres?host=/tmp/banking-demo-socket&user=postgres'
python -m banking_api.db
uvicorn banking_api.main:app --host 0.0.0.0 --port "${PORT:-10000}" --limit-concurrency 24 --timeout-keep-alive 5 --no-access-log &
api_pid=$!
wait "$api_pid"
