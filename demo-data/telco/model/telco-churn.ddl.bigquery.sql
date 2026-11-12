-- ADEF physical DDL | model telco-churn v1.0.0 | dialect BigQuery
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Subscriber (dimension, history: type2) grain: one row per subscriber version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_subscriber (
    subscriber_sk INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_from TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_to TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    is_current BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    subscriber_id STRING NOT NULL OPTIONS(description='Business key'),
    segment STRING OPTIONS(description='Consumer, SME or Enterprise'),
    status STRING OPTIONS(description='ACTIVE, SUSPENDED or CHURNED'),
    activation_date DATE OPTIONS(description='Activation date'),
    msisdn STRING OPTIONS(description='Phone number (masked)'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_code STRING NOT NULL OPTIONS(description='Business key'),
    product_name STRING OPTIONS(description='Product name'),
    product_family STRING OPTIONS(description='Product family'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Subscription Month (fact, history: none) grain: one row per subscriber per month
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_subscription_month (
    subscription_month_id STRING NOT NULL OPTIONS(description='Surrogate business key'),
    subscriber_id STRING OPTIONS(description='Subscriber'),
    product_code STRING OPTIONS(description='Main product'),
    month_start DATE OPTIONS(description='Month'),
    monthly_revenue NUMERIC(12,2) OPTIONS(description='Revenue in month'),
    data_mb NUMERIC(14,2) OPTIONS(description='Data used'),
    voice_min NUMERIC(10,2) OPTIONS(description='Voice minutes'),
    is_churned BOOL OPTIONS(description='Churned in month'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

