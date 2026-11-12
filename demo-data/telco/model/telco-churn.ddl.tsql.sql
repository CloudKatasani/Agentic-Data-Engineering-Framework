-- ADEF physical DDL | model telco-churn v1.0.0 | dialect SQL Server / Synapse / Fabric
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

IF SCHEMA_ID('acme_customer_gold') IS NULL EXEC('CREATE SCHEMA acme_customer_gold');

-- Subscriber (dimension, history: type2) grain: one row per subscriber version
IF OBJECT_ID('acme_customer_gold.dim_subscriber', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_subscriber (
    subscriber_sk BIGINT NOT NULL,
    valid_from DATETIME2(6),
    valid_to DATETIME2(6),
    is_current BIT,
    subscriber_id VARCHAR(20) NOT NULL,
    segment VARCHAR(20),
    status VARCHAR(12),
    activation_date DATE,
    msisdn VARCHAR(15),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_subscriber PRIMARY KEY (subscriber_sk)
);

-- Product (dimension, history: type1) grain: one row per product
IF OBJECT_ID('acme_customer_gold.dim_product', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_product (
    product_code VARCHAR(12) NOT NULL,
    product_name VARCHAR(100),
    product_family VARCHAR(30),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_product PRIMARY KEY (product_code)
);

-- Subscription Month (fact, history: none) grain: one row per subscriber per month
IF OBJECT_ID('acme_customer_gold.fct_subscription_month', 'U') IS NULL
CREATE TABLE acme_customer_gold.fct_subscription_month (
    subscription_month_id VARCHAR(30) NOT NULL,
    subscriber_id VARCHAR(20),
    product_code VARCHAR(12),
    month_start DATE,
    monthly_revenue DECIMAL(12,2),
    data_mb DECIMAL(14,2),
    voice_min DECIMAL(10,2),
    is_churned BIT,
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_subscription_month PRIMARY KEY (subscription_month_id)
);

ALTER TABLE acme_customer_gold.fct_subscription_month ADD CONSTRAINT fk_subscription_month_subscriber_id FOREIGN KEY (subscriber_id) REFERENCES acme_customer_gold.dim_subscriber (subscriber_id);
ALTER TABLE acme_customer_gold.fct_subscription_month ADD CONSTRAINT fk_subscription_month_product_code FOREIGN KEY (product_code) REFERENCES acme_customer_gold.dim_product (product_code);
