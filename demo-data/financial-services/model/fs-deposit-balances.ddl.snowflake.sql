-- ADEF physical DDL | model fs-deposit-balances v1.0.0 | dialect Snowflake
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Customer (dimension, history: type2) grain: one row per customer version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_customer (
    customer_sk NUMBER(38,0) NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    customer_id VARCHAR(20) NOT NULL COMMENT 'Business key',
    segment VARCHAR(20) COMMENT 'Mass, affluent or private',
    kyc_status VARCHAR(10) COMMENT 'VERIFIED, PENDING or EXPIRED',
    full_name VARCHAR(200) COMMENT 'Customer name (masked)',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_customer PRIMARY KEY (customer_sk)
)
COMMENT = 'Bank customer';

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_code VARCHAR(10) NOT NULL COMMENT 'Business key',
    product_name VARCHAR(100) COMMENT 'Product name',
    product_type VARCHAR(20) COMMENT 'Current, savings or term',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_product PRIMARY KEY (product_code)
)
COMMENT = 'Deposit product';

-- Account (dimension, history: type2) grain: one row per account version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_account (
    account_sk NUMBER(38,0) NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    account_id VARCHAR(20) NOT NULL COMMENT 'Business key',
    customer_id VARCHAR(20) COMMENT 'Account holder',
    product_code VARCHAR(10) COMMENT 'Product',
    branch_code VARCHAR(8) COMMENT 'Servicing branch',
    status VARCHAR(10) COMMENT 'OPEN, DORMANT or CLOSED',
    currency VARCHAR(3) COMMENT 'ISO currency',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_account PRIMARY KEY (account_sk)
)
COMMENT = 'Deposit account';

-- Daily Balance (fact, history: none) grain: one row per account per business day
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_daily_balance (
    daily_balance_id VARCHAR(32) NOT NULL COMMENT 'Business key',
    account_id VARCHAR(20) COMMENT 'Account',
    balance_date DATE COMMENT 'Business date',
    ledger_balance NUMBER(18,2) COMMENT 'Ledger balance',
    available_balance NUMBER(18,2) COMMENT 'Available balance',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_daily_balance PRIMARY KEY (daily_balance_id)
)
COMMENT = 'End-of-day deposit balance';

ALTER TABLE acme_customer_gold.dim_account ADD CONSTRAINT fk_account_customer_id FOREIGN KEY (customer_id) REFERENCES acme_customer_gold.dim_customer (customer_id); -- informational (not enforced)
ALTER TABLE acme_customer_gold.dim_account ADD CONSTRAINT fk_account_product_code FOREIGN KEY (product_code) REFERENCES acme_customer_gold.dim_product (product_code); -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_daily_balance ADD CONSTRAINT fk_daily_balance_account_id FOREIGN KEY (account_id) REFERENCES acme_customer_gold.dim_account (account_id); -- informational (not enforced)
