-- ADEF physical DDL | model fs-deposit-balances v1.0.0 | dialect BigQuery
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Customer (dimension, history: type2) grain: one row per customer version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_customer (
    customer_sk INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_from TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_to TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    is_current BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    customer_id STRING NOT NULL OPTIONS(description='Business key'),
    segment STRING OPTIONS(description='Mass, affluent or private'),
    kyc_status STRING OPTIONS(description='VERIFIED, PENDING or EXPIRED'),
    full_name STRING OPTIONS(description='Customer name (masked)'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_code STRING NOT NULL OPTIONS(description='Business key'),
    product_name STRING OPTIONS(description='Product name'),
    product_type STRING OPTIONS(description='Current, savings or term'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Account (dimension, history: type2) grain: one row per account version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_account (
    account_sk INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_from TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_to TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    is_current BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    account_id STRING NOT NULL OPTIONS(description='Business key'),
    customer_id STRING OPTIONS(description='Account holder'),
    product_code STRING OPTIONS(description='Product'),
    branch_code STRING OPTIONS(description='Servicing branch'),
    status STRING OPTIONS(description='OPEN, DORMANT or CLOSED'),
    currency STRING OPTIONS(description='ISO currency'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Daily Balance (fact, history: none) grain: one row per account per business day
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_daily_balance (
    daily_balance_id STRING NOT NULL OPTIONS(description='Business key'),
    account_id STRING OPTIONS(description='Account'),
    balance_date DATE OPTIONS(description='Business date'),
    ledger_balance NUMERIC(18,2) OPTIONS(description='Ledger balance'),
    available_balance NUMERIC(18,2) OPTIONS(description='Available balance'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

