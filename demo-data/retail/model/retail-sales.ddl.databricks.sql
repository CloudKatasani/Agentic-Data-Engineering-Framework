-- ADEF physical DDL | model retail-sales v1.0.0 | dialect Databricks (Delta)
-- Generated 2026-11-12T19:52:54+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Store (dimension, history: type1) grain: one row per store
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_store (
    store_id STRING NOT NULL COMMENT 'Business key',
    store_name STRING COMMENT 'Store name',
    region STRING COMMENT 'Sales region',
    format STRING COMMENT 'FLAGSHIP, STANDARD or EXPRESS',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Physical store';

-- Product (dimension, history: type2) grain: one row per product version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_sk BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    product_id STRING NOT NULL COMMENT 'Business key',
    product_name STRING COMMENT 'Product name',
    category STRING COMMENT 'Category',
    brand STRING COMMENT 'Brand',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Sellable product';

-- Customer (dimension, history: type1) grain: one row per loyalty customer
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_customer (
    customer_id STRING NOT NULL COMMENT 'Business key',
    loyalty_tier STRING COMMENT 'NONE, BRONZE, SILVER or GOLD',
    email STRING COMMENT 'Email (masked)',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Loyalty customer';

-- Sales Line (fact, history: none) grain: one row per order line
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_sales_line (
    order_line_id STRING NOT NULL COMMENT 'Business key',
    order_id STRING COMMENT 'Order (basket)',
    store_id STRING COMMENT 'Store',
    product_id STRING COMMENT 'Product',
    customer_id STRING COMMENT 'Loyalty customer (NONE if anonymous)',
    order_date DATE COMMENT 'Sales date',
    quantity INT COMMENT 'Units',
    net_amount DECIMAL(12,2) COMMENT 'Net sales amount',
    discount_amount DECIMAL(12,2) COMMENT 'Discount',
    load_ts TIMESTAMP COMMENT 'Audit column',
    source_system STRING COMMENT 'Audit column',
    batch_id STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Store sales line';

ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_store_id FOREIGN KEY (store_id) REFERENCES acme_customer_gold.dim_store (store_id) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_product_id FOREIGN KEY (product_id) REFERENCES acme_customer_gold.dim_product (product_id) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_customer_id FOREIGN KEY (customer_id) REFERENCES acme_customer_gold.dim_customer (customer_id) NOT ENFORCED; -- informational (not enforced)
