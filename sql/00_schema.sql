DROP TABLE IF EXISTS fx_transactions CASCADE;
DROP TABLE IF EXISTS transfers CASCADE;
DROP TABLE IF EXISTS card_transactions CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS product_events CASCADE;
DROP TABLE IF EXISTS experiment_assignments CASCADE;
DROP TABLE IF EXISTS marketing_spend CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;
DROP TABLE IF EXISTS kyc_cases CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    signup_ts TIMESTAMP NOT NULL,
    country_code CHAR(2) NOT NULL,
    age SMALLINT NOT NULL CHECK (age BETWEEN 18 AND 100),
    acquisition_channel VARCHAR(30) NOT NULL
        CHECK (acquisition_channel IN
            ('organic','paid_search','paid_social','referral','affiliate')),
    device_os VARCHAR(20) NOT NULL
        CHECK (device_os IN ('iOS','Android')),
    referral_code_used BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE kyc_cases (
    kyc_case_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    started_ts TIMESTAMP,
    completed_ts TIMESTAMP,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('approved','rejected','abandoned')),
    failure_reason VARCHAR(40)
);

CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE REFERENCES customers(customer_id),
    opened_ts TIMESTAMP NOT NULL,
    plan_tier VARCHAR(20) NOT NULL
        CHECK (plan_tier IN ('standard','premium')),
    base_currency CHAR(3) NOT NULL
        CHECK (base_currency IN ('GBP','EUR'))
);

CREATE TABLE marketing_spend (
    spend_month DATE NOT NULL,
    acquisition_channel VARCHAR(30) NOT NULL,
    spend_gbp NUMERIC(14,2) NOT NULL CHECK (spend_gbp >= 0),
    impressions BIGINT NOT NULL CHECK (impressions >= 0),
    clicks BIGINT NOT NULL CHECK (clicks >= 0),
    PRIMARY KEY (spend_month, acquisition_channel)
);

CREATE TABLE experiment_assignments (
    assignment_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    experiment_name VARCHAR(80) NOT NULL,
    variant VARCHAR(30) NOT NULL CHECK (variant IN ('control','bonus_10')),
    assigned_ts TIMESTAMP NOT NULL,
    UNIQUE (customer_id, experiment_name)
);

CREATE TABLE product_events (
    event_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    event_ts TIMESTAMP NOT NULL,
    event_name VARCHAR(50) NOT NULL,
    session_id VARCHAR(40),
    event_value NUMERIC(14,2)
);

CREATE TABLE transactions (
    transaction_id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(account_id),
    transaction_ts TIMESTAMP NOT NULL,
    transaction_type VARCHAR(30) NOT NULL
        CHECK (transaction_type IN
            ('cash_in','card_payment','bank_transfer','fx_exchange','cash_withdrawal')),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('completed','failed','reversed')),
    amount_gbp NUMERIC(14,2) NOT NULL CHECK (amount_gbp >= 0),
    fee_revenue_gbp NUMERIC(12,2) NOT NULL DEFAULT 0,
    interchange_revenue_gbp NUMERIC(12,2) NOT NULL DEFAULT 0,
    fx_spread_revenue_gbp NUMERIC(12,2) NOT NULL DEFAULT 0,
    processing_cost_gbp NUMERIC(12,2) NOT NULL DEFAULT 0,
    incentive_cost_gbp NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE card_transactions (
    transaction_id BIGINT PRIMARY KEY REFERENCES transactions(transaction_id),
    merchant_category VARCHAR(50),
    merchant_country CHAR(2),
    card_present BOOLEAN
);

CREATE TABLE transfers (
    transaction_id BIGINT PRIMARY KEY REFERENCES transactions(transaction_id),
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('inbound','outbound')),
    transfer_rail VARCHAR(20) NOT NULL
        CHECK (transfer_rail IN ('faster_payments','sepa','swift')),
    counterparty_country CHAR(2)
);

CREATE TABLE fx_transactions (
    transaction_id BIGINT PRIMARY KEY REFERENCES transactions(transaction_id),
    from_currency CHAR(3) NOT NULL,
    to_currency CHAR(3) NOT NULL,
    source_amount NUMERIC(14,2) NOT NULL,
    target_amount NUMERIC(14,2) NOT NULL,
    quoted_rate NUMERIC(18,8) NOT NULL,
    spread_bps NUMERIC(10,2) NOT NULL
);

CREATE INDEX idx_customers_signup_ts ON customers(signup_ts);
CREATE INDEX idx_customers_channel ON customers(acquisition_channel);
CREATE INDEX idx_kyc_customer ON kyc_cases(customer_id);
CREATE INDEX idx_accounts_customer ON accounts(customer_id);
CREATE INDEX idx_events_customer_ts ON product_events(customer_id, event_ts);
CREATE INDEX idx_events_name_ts ON product_events(event_name, event_ts);
CREATE INDEX idx_transactions_account_ts ON transactions(account_id, transaction_ts);
CREATE INDEX idx_transactions_type_ts ON transactions(transaction_type, transaction_ts);
