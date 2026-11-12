-- ADPE physical DDL | model retail-sales v1.0.0 | dialect Snowflake
-- Generated 2026-11-12T19:20:16+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS acme_customer_gold;

-- Store (dimension, history: type1) grain: one row per store
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_store (
    store_id VARCHAR(10) NOT NULL COMMENT 'Business key',
    store_name VARCHAR(100) COMMENT 'Store name',
    region VARCHAR(20) COMMENT 'Sales region',
    format VARCHAR(12) COMMENT 'FLAGSHIP, STANDARD or EXPRESS',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_store PRIMARY KEY (store_id)
)
COMMENT = 'Physical store';

-- Product (dimension, history: type2) grain: one row per product version
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_product (
    product_sk NUMBER(38,0) NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    valid_from TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    valid_to TIMESTAMP_NTZ COMMENT 'Surrogate key / history column (type 2)',
    is_current BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    product_id VARCHAR(14) NOT NULL COMMENT 'Business key',
    product_name VARCHAR(200) COMMENT 'Product name',
    category VARCHAR(40) COMMENT 'Category',
    brand VARCHAR(40) COMMENT 'Brand',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_product PRIMARY KEY (product_sk)
)
COMMENT = 'Sellable product';

-- Customer (dimension, history: type1) grain: one row per loyalty customer
CREATE TABLE IF NOT EXISTS acme_customer_gold.dim_customer (
    customer_id VARCHAR(20) NOT NULL COMMENT 'Business key',
    loyalty_tier VARCHAR(10) COMMENT 'NONE, BRONZE, SILVER or GOLD',
    email VARCHAR(200) COMMENT 'Email (masked)',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_customer PRIMARY KEY (customer_id)
)
COMMENT = 'Loyalty customer';

-- Sales Line (fact, history: none) grain: one row per order line
CREATE TABLE IF NOT EXISTS acme_customer_gold.fct_sales_line (
    order_line_id VARCHAR(24) NOT NULL COMMENT 'Business key',
    order_id VARCHAR(20) COMMENT 'Order (basket)',
    store_id VARCHAR(10) COMMENT 'Store',
    product_id VARCHAR(14) COMMENT 'Product',
    customer_id VARCHAR(20) COMMENT 'Loyalty customer (NONE if anonymous)',
    order_date DATE COMMENT 'Sales date',
    quantity NUMBER(38,0) COMMENT 'Units',
    net_amount NUMBER(12,2) COMMENT 'Net sales amount',
    discount_amount NUMBER(12,2) COMMENT 'Discount',
    load_ts TIMESTAMP_NTZ COMMENT 'Audit column',
    source_system VARCHAR(64) COMMENT 'Audit column',
    batch_id VARCHAR(64) COMMENT 'Audit column',
    CONSTRAINT pk_sales_line PRIMARY KEY (order_line_id)
)
COMMENT = 'Store sales line';

ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_store_id FOREIGN KEY (store_id) REFERENCES acme_customer_gold.dim_store (store_id); -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_product_id FOREIGN KEY (product_id) REFERENCES acme_customer_gold.dim_product (product_id); -- informational (not enforced)
ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_customer_id FOREIGN KEY (customer_id) REFERENCES acme_customer_gold.dim_customer (customer_id); -- informational (not enforced)
