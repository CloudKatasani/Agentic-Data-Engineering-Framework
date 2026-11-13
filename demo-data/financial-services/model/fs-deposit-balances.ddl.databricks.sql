-- ADEF physical DDL | model fs-deposit-balances v1.0.0 | dialect Databricks (Delta)
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Customer (dimension, history: type2) grain: one row per customer version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_customer (
    customer_sk BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    customer_id STRING NOT NULL COMMENT 'Business key',
    segment STRING COMMENT 'Mass, affluent or private',
    kyc_status STRING COMMENT 'VERIFIED, PENDING or EXPIRED',
    full_name STRING COMMENT 'Customer name (masked)',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Bank customer';

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_code STRING NOT NULL COMMENT 'Business key',
    product_name STRING COMMENT 'Product name',
    product_type STRING COMMENT 'Current, savings or term',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Deposit product';

-- Account (dimension, history: type2) grain: one row per account version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_account (
    account_sk BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    account_id STRING NOT NULL COMMENT 'Business key',
    customer_id STRING COMMENT 'Account holder',
    product_code STRING COMMENT 'Product',
    branch_code STRING COMMENT 'Servicing branch',
    status STRING COMMENT 'OPEN, DORMANT or CLOSED',
    currency STRING COMMENT 'ISO currency',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Deposit account';

-- Daily Balance (fact, history: none) grain: one row per account per business day
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_daily_balance (
    daily_balance_id STRING NOT NULL COMMENT 'Business key',
    account_id STRING COMMENT 'Account',
    balance_date DATE COMMENT 'Business date',
    ledger_balance DECIMAL(18,2) COMMENT 'Ledger balance',
    available_balance DECIMAL(18,2) COMMENT 'Available balance',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'End-of-day deposit balance';

ALTER TABLE acme_customer_gold.dim_account ADD CONSTRAINT fk_account_customer_id FOREIGN KEY (customer_id) REFERENCES acme_customer_gold.dim_customer (customer_id) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE acme_customer_gold.dim_account ADD CONSTRAINT fk_account_product_code FOREIGN KEY (product_code) REFERENCES acme_customer_gold.dim_product (product_code) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_daily_balance ADD CONSTRAINT fk_daily_balance_account_id FOREIGN KEY (account_id) REFERENCES acme_customer_gold.dim_account (account_id) NOT ENFORCED; -- informational (not enforced)
