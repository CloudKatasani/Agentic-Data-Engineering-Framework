-- ADEF physical DDL | model telco-churn v1.0.0 | dialect Snowflake
-- Generated 2026-11-12T19:52:54+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Subscriber (dimension, history: type2) grain: one row per subscriber version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_subscriber (
    subscriber_sk NUMBER(38,0) NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    subscriber_id VARCHAR(20) NOT NULL COMMENT 'Business key',
    segment VARCHAR(20) COMMENT 'Consumer, SME or Enterprise',
    status VARCHAR(12) COMMENT 'ACTIVE, SUSPENDED or CHURNED',
    activation_date DATE COMMENT 'Activation date',
    msisdn VARCHAR(15) COMMENT 'Phone number (masked)',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_subscriber PRIMARY KEY (subscriber_sk)
)
COMMENT = 'Mobile subscriber';

-- Product (dimension, history: type1) grain: one row per product
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_code VARCHAR(12) NOT NULL COMMENT 'Business key',
    product_name VARCHAR(100) COMMENT 'Product name',
    product_family VARCHAR(30) COMMENT 'Product family',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_product PRIMARY KEY (product_code)
)
COMMENT = 'Product offering';

-- Subscription Month (fact, history: none) grain: one row per subscriber per month
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_subscription_month (
    subscription_month_id VARCHAR(30) NOT NULL COMMENT 'Surrogate business key',
    subscriber_id VARCHAR(20) COMMENT 'Subscriber',
    product_code VARCHAR(12) COMMENT 'Main product',
    month_start DATE COMMENT 'Month',
    monthly_revenue NUMBER(12,2) COMMENT 'Revenue in month',
    data_mb NUMBER(14,2) COMMENT 'Data used',
    voice_min NUMBER(10,2) COMMENT 'Voice minutes',
    is_churned BOOLEAN COMMENT 'Churned in month',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_subscription_month PRIMARY KEY (subscription_month_id)
)
COMMENT = 'Monthly revenue, usage and churn per subscriber';

ALTER TABLE acme_customer_gold.fct_subscription_month ADD CONSTRAINT fk_subscription_month_subscriber_id FOREIGN KEY (subscriber_id) REFERENCES acme_customer_gold.dim_subscriber (subscriber_id); -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_subscription_month ADD CONSTRAINT fk_subscription_month_product_code FOREIGN KEY (product_code) REFERENCES acme_customer_gold.dim_product (product_code); -- informational (not enforced)
