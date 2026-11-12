-- ADPE physical DDL | model retail-sales v1.0.0 | dialect BigQuery
-- Generated 2026-11-12T19:20:16+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Store (dimension, history: type1) grain: one row per store
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_store (
    store_id STRING NOT NULL OPTIONS(description='Business key'),
    store_name STRING OPTIONS(description='Store name'),
    region STRING OPTIONS(description='Sales region'),
    format STRING OPTIONS(description='FLAGSHIP, STANDARD or EXPRESS'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Product (dimension, history: type2) grain: one row per product version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_sk INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_from TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    valid_to TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    is_current BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    product_id STRING NOT NULL OPTIONS(description='Business key'),
    product_name STRING OPTIONS(description='Product name'),
    category STRING OPTIONS(description='Category'),
    brand STRING OPTIONS(description='Brand'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Customer (dimension, history: type1) grain: one row per loyalty customer
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_customer (
    customer_id STRING NOT NULL OPTIONS(description='Business key'),
    loyalty_tier STRING OPTIONS(description='NONE, BRONZE, SILVER or GOLD'),
    email STRING OPTIONS(description='Email (masked)'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

-- Sales Line (fact, history: none) grain: one row per order line
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_sales_line (
    order_line_id STRING NOT NULL OPTIONS(description='Business key'),
    order_id STRING OPTIONS(description='Order (basket)'),
    store_id STRING OPTIONS(description='Store'),
    product_id STRING OPTIONS(description='Product'),
    customer_id STRING OPTIONS(description='Loyalty customer (NONE if anonymous)'),
    order_date DATE OPTIONS(description='Sales date'),
    quantity INT64 OPTIONS(description='Units'),
    net_amount NUMERIC(12,2) OPTIONS(description='Net sales amount'),
    discount_amount NUMERIC(12,2) OPTIONS(description='Discount'),
    load_ts TIMESTAMP OPTIONS(description='Audit column'),
    source_system STRING OPTIONS(description='Audit column'),
    batch_id STRING OPTIONS(description='Audit column')
);

