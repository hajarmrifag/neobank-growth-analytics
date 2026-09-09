-- Separate from the historical analytics tables. Money is stored in pence.
CREATE SCHEMA IF NOT EXISTS banking;

CREATE TABLE IF NOT EXISTS banking.demo_sessions (
    id UUID PRIMARY KEY,
    token_hash TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp() + INTERVAL '30 minutes',
    window_start TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    request_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS banking.accounts (
    id UUID PRIMARY KEY,
    owner_name TEXT NOT NULL CHECK (length(owner_name) BETWEEN 1 AND 100),
    currency TEXT NOT NULL DEFAULT 'GBP' CHECK (currency = 'GBP'),
    opening_balance_minor BIGINT NOT NULL CHECK (opening_balance_minor BETWEEN 0 AND 1000000000000),
    balance_minor BIGINT NOT NULL CHECK (balance_minor BETWEEN 0 AND 9000000000000000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS banking.transfers (
    id UUID PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    source_account_id UUID NOT NULL REFERENCES banking.accounts(id),
    destination_account_id UUID NOT NULL REFERENCES banking.accounts(id),
    amount_minor BIGINT NOT NULL CHECK (amount_minor BETWEEN 1 AND 1000000000000),
    currency TEXT NOT NULL DEFAULT 'GBP' CHECK (currency = 'GBP'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (source_account_id <> destination_account_id)
);

CREATE INDEX IF NOT EXISTS transfers_source_history_idx
    ON banking.transfers (source_account_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS transfers_destination_history_idx
    ON banking.transfers (destination_account_id, created_at DESC, id DESC);

ALTER TABLE banking.accounts ADD COLUMN IF NOT EXISTS demo_session_id UUID
    REFERENCES banking.demo_sessions(id);
CREATE INDEX IF NOT EXISTS accounts_demo_session_idx ON banking.accounts(demo_session_id);
