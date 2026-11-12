-- Source system DDL (utilities) - synthetic, for metadata import demos

CREATE TABLE cis.account (
    account_id VARCHAR(20) NOT NULL,
    customer_name VARCHAR(200),
    service_address VARCHAR(400),
    account_status VARCHAR(1),
    rate_class VARCHAR(10),
    open_date DATE,
    close_date DATE,
    updated_at TIMESTAMP,
    PRIMARY KEY (account_id)
);

CREATE TABLE cis.premise (
    premise_id VARCHAR(20) NOT NULL,
    account_id VARCHAR(20),
    premise_type VARCHAR(20),
    region_code VARCHAR(10),
    postal_code VARCHAR(10),
    PRIMARY KEY (premise_id)
);

CREATE TABLE mdm.meter (
    meter_id VARCHAR(20) NOT NULL,
    premise_id VARCHAR(20),
    meter_type VARCHAR(10),
    install_date DATE,
    status VARCHAR(10),
    PRIMARY KEY (meter_id)
);

CREATE TABLE mdm.daily_read (
    meter_id VARCHAR(20) NOT NULL,
    read_date DATE NOT NULL,
    kwh DECIMAL(18,3),
    read_quality VARCHAR(1),
    loaded_at TIMESTAMP,
    PRIMARY KEY (meter_id, read_date)
);

CREATE TABLE cis.bill (
    bill_id VARCHAR(20) NOT NULL,
    account_id VARCHAR(20),
    period_start DATE,
    period_end DATE,
    billed_kwh DECIMAL(18,3),
    amount_due DECIMAL(18,2),
    bill_status VARCHAR(10),
    PRIMARY KEY (bill_id)
);
