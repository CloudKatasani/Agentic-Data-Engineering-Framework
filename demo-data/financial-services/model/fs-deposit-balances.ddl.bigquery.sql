-- ADEF physical DDL | model fs-deposit-balances v1.0.0 | dialect BigQuery
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS ACME_CUSTOMER_CURATED;

-- Customer (dimension, history: type2) grain: one row per customer version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_CUSTOMER (
    CUSTOMER_SK INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    VALID_FROM TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    VALID_TO TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    IS_CURRENT BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    CUSTOMER_ID STRING NOT NULL OPTIONS(description='Business key'),
    SEGMENT STRING OPTIONS(description='Mass, affluent or private'),
    KYC_STATUS STRING OPTIONS(description='VERIFIED, PENDING or EXPIRED'),
    FULL_NAME STRING OPTIONS(description='Customer name (masked)'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_PRODUCT (
    PRODUCT_CODE STRING NOT NULL OPTIONS(description='Business key'),
    PRODUCT_NAME STRING OPTIONS(description='Product name'),
    PRODUCT_TYPE STRING OPTIONS(description='Current, savings or term'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

-- Account (dimension, history: type2) grain: one row per account version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_ACCOUNT (
    ACCOUNT_SK INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    VALID_FROM TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    VALID_TO TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    IS_CURRENT BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    ACCOUNT_ID STRING NOT NULL OPTIONS(description='Business key'),
    CUSTOMER_ID STRING OPTIONS(description='Account holder'),
    PRODUCT_CODE STRING OPTIONS(description='Product'),
    BRANCH_CODE STRING OPTIONS(description='Servicing branch'),
    STATUS STRING OPTIONS(description='OPEN, DORMANT or CLOSED'),
    CURRENCY STRING OPTIONS(description='ISO currency'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

-- Daily Balance (fact, history: none) grain: one row per account per business day
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.FCT_DAILY_BALANCE (
    DAILY_BALANCE_ID STRING NOT NULL OPTIONS(description='Business key'),
    ACCOUNT_ID STRING OPTIONS(description='Account'),
    BALANCE_DATE DATE OPTIONS(description='Business date'),
    LEDGER_BALANCE NUMERIC(18,2) OPTIONS(description='Ledger balance'),
    AVAILABLE_BALANCE NUMERIC(18,2) OPTIONS(description='Available balance'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

