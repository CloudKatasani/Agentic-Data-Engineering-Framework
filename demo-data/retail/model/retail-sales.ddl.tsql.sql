-- ADEF physical DDL | model retail-sales v1.0.0 | dialect SQL Server / Synapse / Fabric
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

IF SCHEMA_ID('acme_customer_gold') IS NULL EXEC('CREATE SCHEMA acme_customer_gold');

-- Store (dimension, history: type1) grain: one row per store
IF OBJECT_ID('acme_customer_gold.dim_store', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_store (
    store_id VARCHAR(10) NOT NULL,
    store_name VARCHAR(100),
    region VARCHAR(20),
    format VARCHAR(12),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_store PRIMARY KEY (store_id)
);

-- Product (dimension, history: type2) grain: one row per product version
IF OBJECT_ID('acme_customer_gold.dim_product', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_product (
    product_sk BIGINT NOT NULL,
    valid_from DATETIME2(6),
    valid_to DATETIME2(6),
    is_current BIT,
    product_id VARCHAR(14) NOT NULL,
    product_name VARCHAR(200),
    category VARCHAR(40),
    brand VARCHAR(40),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_product PRIMARY KEY (product_sk)
);

-- Customer (dimension, history: type1) grain: one row per loyalty customer
IF OBJECT_ID('acme_customer_gold.dim_customer', 'U') IS NULL
CREATE TABLE acme_customer_gold.dim_customer (
    customer_id VARCHAR(20) NOT NULL,
    loyalty_tier VARCHAR(10),
    email VARCHAR(200),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);

-- Sales Line (fact, history: none) grain: one row per order line
IF OBJECT_ID('acme_customer_gold.fct_sales_line', 'U') IS NULL
CREATE TABLE acme_customer_gold.fct_sales_line (
    order_line_id VARCHAR(24) NOT NULL,
    order_id VARCHAR(20),
    store_id VARCHAR(10),
    product_id VARCHAR(14),
    customer_id VARCHAR(20),
    order_date DATE,
    quantity INT,
    net_amount DECIMAL(12,2),
    discount_amount DECIMAL(12,2),
    load_ts DATETIME2(6),
    source_system VARCHAR(64),
    batch_id VARCHAR(64),
    CONSTRAINT pk_sales_line PRIMARY KEY (order_line_id)
);

ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_store_id FOREIGN KEY (store_id) REFERENCES acme_customer_gold.dim_store (store_id);
ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_product_id FOREIGN KEY (product_id) REFERENCES acme_customer_gold.dim_product (product_id);
ALTER TABLE acme_customer_gold.fct_sales_line ADD CONSTRAINT fk_sales_line_customer_id FOREIGN KEY (customer_id) REFERENCES acme_customer_gold.dim_customer (customer_id);
