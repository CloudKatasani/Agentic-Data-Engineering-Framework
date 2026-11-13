-- ADEF physical DDL | model fs-deposit-balances v1.0.0 | dialect SQL Server / Synapse / Fabric
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

IF SCHEMA_ID('acme_customer_gold') IS NULL EXEC('CREATE SCHEMA acme_customer_gold');

-- Customer (dimension, history: type2) grain: one row per customer version
IF OBJECT_ID('acme_customer_gold.dim_customer', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_customer (
    customer_sk BIGINT NOT NULL,
    valid_from DATETIME2(6),
    valid_to DATETIME2(6),
    is_current BIT,
    customer_id VARCHAR(20) NOT NULL,
    segment VARCHAR(20),
    kyc_status VARCHAR(10),
    full_name VARCHAR(200),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_customer PRIMARY KEY (customer_sk)
);

-- Product (dimension, history: type1) grain: one row per product
IF OBJECT_ID('acme_customer_gold.dim_product', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_product (
    product_code VARCHAR(10) NOT NULL,
    product_name VARCHAR(100),
    product_type VARCHAR(20),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_product PRIMARY KEY (product_code)
);

-- Account (dimension, history: type2) grain: one row per account version
IF OBJECT_ID('acme_customer_gold.dim_account', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_account (
    account_sk BIGINT NOT NULL,
    valid_from DATETIME2(6),
    valid_to DATETIME2(6),
    is_current BIT,
    account_id VARCHAR(20) NOT NULL,
    customer_id VARCHAR(20),
    product_code VARCHAR(10),
    branch_code VARCHAR(8),
    status VARCHAR(10),
    currency VARCHAR(3),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_account PRIMARY KEY (account_sk)
);

-- Daily Balance (fact, history: none) grain: one row per account per business day
IF OBJECT_ID('acme_customer_gold.fct_daily_balance', 'U') IS NULL
CREATE TABLE acme_customer_gold.fct_daily_balance (
    daily_balance_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(20),
    balance_date DATE,
    ledger_balance DECIMAL(18,2),
    available_balance DECIMAL(18,2),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_daily_balance PRIMARY KEY (daily_balance_id)
);

ALTER TABLE acme_customer_gold.dim_account ADD CONSTRAINT fk_account_customer_id FOREIGN KEY (customer_id) REFERENCES acme_customer_gold.dim_customer (customer_id);
ALTER TABLE acme_customer_gold.dim_account ADD CONSTRAINT fk_account_product_code FOREIGN KEY (product_code) REFERENCES acme_customer_gold.dim_product (product_code);
ALTER TABLE acme_customer_gold.fct_daily_balance ADD CONSTRAINT fk_daily_balance_account_id FOREIGN KEY (account_id) REFERENCES acme_customer_gold.dim_account (account_id);
