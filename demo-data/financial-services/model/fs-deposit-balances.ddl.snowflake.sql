-- ADEF physical DDL | model fs-deposit-balances v1.0.0 | dialect Snowflake
-- Generated 2026-11-12T19:52:54+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS ACME_CUSTOMER_CURATED;

-- Customer (dimension, history: type2) grain: one row per customer version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_CUSTOMER (
    CUSTOMER_SK NUMBER(38,0) NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    VALID_FROM TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    VALID_TO TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    IS_CURRENT BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    CUSTOMER_ID VARCHAR(20) NOT NULL COMMENT 'Business key',
    SEGMENT VARCHAR(20) COMMENT 'Mass, affluent or private',
    KYC_STATUS VARCHAR(10) COMMENT 'VERIFIED, PENDING or EXPIRED',
    FULL_NAME VARCHAR(200) COMMENT 'Customer name (masked)',
    LOAD_TS TIMESTAMP_NTZ COMMENT 'Audit column',
    SOURCE_SYSTEM VARCHAR(64) COMMENT 'Audit column',
    BATCH_ID VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_customer PRIMARY KEY (CUSTOMER_SK)
)
COMMENT = 'Bank customer';

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_PRODUCT (
    PRODUCT_CODE VARCHAR(10) NOT NULL COMMENT 'Business key',
    PRODUCT_NAME VARCHAR(100) COMMENT 'Product name',
    PRODUCT_TYPE VARCHAR(20) COMMENT 'Current, savings or term',
    LOAD_TS TIMESTAMP_NTZ COMMENT 'Audit column',
    SOURCE_SYSTEM VARCHAR(64) COMMENT 'Audit column',
    BATCH_ID VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_product PRIMARY KEY (PRODUCT_CODE)
)
COMMENT = 'Deposit product';

-- Account (dimension, history: type2) grain: one row per account version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_ACCOUNT (
    ACCOUNT_SK NUMBER(38,0) NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    VALID_FROM TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    VALID_TO TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    IS_CURRENT BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    ACCOUNT_ID VARCHAR(20) NOT NULL COMMENT 'Business key',
    CUSTOMER_ID VARCHAR(20) COMMENT 'Account holder',
    PRODUCT_CODE VARCHAR(10) COMMENT 'Product',
    BRANCH_CODE VARCHAR(8) COMMENT 'Servicing branch',
    STATUS VARCHAR(10) COMMENT 'OPEN, DORMANT or CLOSED',
    CURRENCY VARCHAR(3) COMMENT 'ISO currency',
    LOAD_TS TIMESTAMP_NTZ COMMENT 'Audit column',
    SOURCE_SYSTEM VARCHAR(64) COMMENT 'Audit column',
    BATCH_ID VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_account PRIMARY KEY (ACCOUNT_SK)
)
COMMENT = 'Deposit account';

-- Daily Balance (fact, history: none) grain: one row per account per business day
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.FCT_DAILY_BALANCE (
    DAILY_BALANCE_ID VARCHAR(32) NOT NULL COMMENT 'Business key',
    ACCOUNT_ID VARCHAR(20) COMMENT 'Account',
    BALANCE_DATE DATE COMMENT 'Business date',
    LEDGER_BALANCE NUMBER(18,2) COMMENT 'Ledger balance',
    AVAILABLE_BALANCE NUMBER(18,2) COMMENT 'Available balance',
    LOAD_TS TIMESTAMP_NTZ COMMENT 'Audit column',
    SOURCE_SYSTEM VARCHAR(64) COMMENT 'Audit column',
    BATCH_ID VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_daily_balance PRIMARY KEY (DAILY_BALANCE_ID)
)
COMMENT = 'End-of-day deposit balance';

ALTER TABLE ACME_CUSTOMER_CURATED.DIM_ACCOUNT ADD CONSTRAINT fk_account_customer_id FOREIGN KEY (CUSTOMER_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_CUSTOMER (CUSTOMER_ID); -- informational (not enforced)
ALTER TABLE ACME_CUSTOMER_CURATED.DIM_ACCOUNT ADD CONSTRAINT fk_account_product_code FOREIGN KEY (PRODUCT_CODE) REFERENCES ACME_CUSTOMER_CURATED.DIM_PRODUCT (PRODUCT_CODE); -- informational (not enforced)
ALTER TABLE ACME_CUSTOMER_CURATED.FCT_DAILY_BALANCE ADD CONSTRAINT fk_daily_balance_account_id FOREIGN KEY (ACCOUNT_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_ACCOUNT (ACCOUNT_ID); -- informational (not enforced)
