-- ADPE physical DDL | model fs-deposit-balances v1.0.0 | dialect Databricks (Delta)
-- Generated 2026-11-12T19:20:16+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS ACME_CUSTOMER_CURATED;

-- Customer (dimension, history: type2) grain: one row per customer version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_CUSTOMER (
    CUSTOMER_SK BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    VALID_FROM TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    VALID_TO TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    IS_CURRENT BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    CUSTOMER_ID STRING NOT NULL COMMENT 'Business key',
    SEGMENT STRING COMMENT 'Mass, affluent or private',
    KYC_STATUS STRING COMMENT 'VERIFIED, PENDING or EXPIRED',
    FULL_NAME STRING COMMENT 'Customer name (masked)',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Bank customer';

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_PRODUCT (
    PRODUCT_CODE STRING NOT NULL COMMENT 'Business key',
    PRODUCT_NAME STRING COMMENT 'Product name',
    PRODUCT_TYPE STRING COMMENT 'Current, savings or term',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Deposit product';

-- Account (dimension, history: type2) grain: one row per account version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_ACCOUNT (
    ACCOUNT_SK BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    VALID_FROM TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    VALID_TO TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    IS_CURRENT BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    ACCOUNT_ID STRING NOT NULL COMMENT 'Business key',
    CUSTOMER_ID STRING COMMENT 'Account holder',
    PRODUCT_CODE STRING COMMENT 'Product',
    BRANCH_CODE STRING COMMENT 'Servicing branch',
    STATUS STRING COMMENT 'OPEN, DORMANT or CLOSED',
    CURRENCY STRING COMMENT 'ISO currency',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Deposit account';

-- Daily Balance (fact, history: none) grain: one row per account per business day
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.FCT_DAILY_BALANCE (
    DAILY_BALANCE_ID STRING NOT NULL COMMENT 'Business key',
    ACCOUNT_ID STRING COMMENT 'Account',
    BALANCE_DATE DATE COMMENT 'Business date',
    LEDGER_BALANCE DECIMAL(18,2) COMMENT 'Ledger balance',
    AVAILABLE_BALANCE DECIMAL(18,2) COMMENT 'Available balance',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'End-of-day deposit balance';

ALTER TABLE ACME_CUSTOMER_CURATED.DIM_ACCOUNT ADD CONSTRAINT fk_account_customer_id FOREIGN KEY (CUSTOMER_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_CUSTOMER (CUSTOMER_ID) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE ACME_CUSTOMER_CURATED.DIM_ACCOUNT ADD CONSTRAINT fk_account_product_code FOREIGN KEY (PRODUCT_CODE) REFERENCES ACME_CUSTOMER_CURATED.DIM_PRODUCT (PRODUCT_CODE) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE ACME_CUSTOMER_CURATED.FCT_DAILY_BALANCE ADD CONSTRAINT fk_daily_balance_account_id FOREIGN KEY (ACCOUNT_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_ACCOUNT (ACCOUNT_ID) NOT ENFORCED; -- informational (not enforced)
