-- Source system DDL (retail) - synthetic, for metadata import demos

CREATE TABLE pos.store (
    store_id VARCHAR(10) NOT NULL,
    store_name VARCHAR(100),
    region VARCHAR(20),
    format VARCHAR(12),
    PRIMARY KEY (store_id)
);

CREATE TABLE pim.product (
    product_id VARCHAR(14) NOT NULL,
    product_name VARCHAR(200),
    category VARCHAR(40),
    brand VARCHAR(40),
    list_price DECIMAL(10,2),
    unit_cost DECIMAL(10,2),
    PRIMARY KEY (product_id)
);

CREATE TABLE crm.customer (
    customer_id VARCHAR(20) NOT NULL,
    email VARCHAR(200),
    loyalty_tier VARCHAR(10),
    consent_marketing BOOLEAN,
    PRIMARY KEY (customer_id)
);

CREATE TABLE pos.order_line (
    order_line_id VARCHAR(24) NOT NULL,
    order_id VARCHAR(20),
    store_id VARCHAR(10),
    product_id VARCHAR(14),
    customer_id VARCHAR(20),
    order_ts TIMESTAMP,
    quantity INTEGER,
    gross_amount DECIMAL(12,2),
    discount_amount DECIMAL(12,2),
    return_flag VARCHAR(1),
    PRIMARY KEY (order_line_id)
);
