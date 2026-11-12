-- Source system DDL (financial-services) - synthetic, for metadata import demos

CREATE TABLE cbs.customer (
    customer_id VARCHAR(20) NOT NULL,
    full_name VARCHAR(200),
    national_id VARCHAR(20),
    date_of_birth DATE,
    segment VARCHAR(20),
    kyc_status VARCHAR(10),
    onboard_date DATE,
    PRIMARY KEY (customer_id)
);

CREATE TABLE cbs.account (
    account_id VARCHAR(20) NOT NULL,
    customer_id VARCHAR(20),
    product_code VARCHAR(10),
    branch_code VARCHAR(8),
    open_date DATE,
    status VARCHAR(10),
    currency VARCHAR(3),
    PRIMARY KEY (account_id)
);

CREATE TABLE cbs.product (
    product_code VARCHAR(10) NOT NULL,
    product_name VARCHAR(100),
    product_type VARCHAR(20),
    interest_rate DECIMAL(7,4),
    PRIMARY KEY (product_code)
);

CREATE TABLE cbs.daily_balance (
    account_id VARCHAR(20) NOT NULL,
    balance_date DATE NOT NULL,
    ledger_balance DECIMAL(18,2),
    available_balance DECIMAL(18,2),
    PRIMARY KEY (account_id, balance_date)
);
