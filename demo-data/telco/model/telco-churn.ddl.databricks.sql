-- ADEF physical DDL | model telco-churn v1.0.0 | dialect Databricks (Delta)
-- Generated 2026-11-12T19:52:54+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Subscriber (dimension, history: type2) grain: one row per subscriber version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_subscriber (
    subscriber_sk BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    subscriber_id STRING NOT NULL COMMENT 'Business key',
    segment STRING COMMENT 'Consumer, SME or Enterprise',
    status STRING COMMENT 'ACTIVE, SUSPENDED or CHURNED',
    activation_date DATE COMMENT 'Activation date',
    msisdn STRING COMMENT 'Phone number (masked)',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Mobile subscriber';

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_code STRING NOT NULL COMMENT 'Business key',
    product_name STRING COMMENT 'Product name',
    product_family STRING COMMENT 'Product family',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Product offering';

-- Subscription Month (fact, history: none) grain: one row per subscriber per month
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_subscription_month (
    subscription_month_id STRING NOT NULL COMMENT 'Surrogate business key',
    subscriber_id STRING COMMENT 'Subscriber',
    product_code STRING COMMENT 'Main product',
    month_start DATE COMMENT 'Month',
    monthly_revenue DECIMAL(12,2) COMMENT 'Revenue in month',
    data_mb DECIMAL(14,2) COMMENT 'Data used',
    voice_min DECIMAL(10,2) COMMENT 'Voice minutes',
    is_churned BOOLEAN COMMENT 'Churned in month',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Monthly revenue, usage and churn per subscriber';

ALTER TABLE acme_customer_gold.fct_subscription_month ADD CONSTRAINT fk_subscription_month_subscriber_id FOREIGN KEY (subscriber_id) REFERENCES acme_customer_gold.dim_subscriber (subscriber_id) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_subscription_month ADD CONSTRAINT fk_subscription_month_product_code FOREIGN KEY (product_code) REFERENCES acme_customer_gold.dim_product (product_code) NOT ENFORCED; -- informational (not enforced)
