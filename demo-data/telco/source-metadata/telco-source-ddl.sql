-- Source system DDL (telco) - synthetic, for metadata import demos

CREATE TABLE crm.subscriber (
    subscriber_id VARCHAR(20) NOT NULL,
    msisdn VARCHAR(15),
    full_name VARCHAR(200),
    segment VARCHAR(20),
    activation_date DATE,
    status VARCHAR(12),
    PRIMARY KEY (subscriber_id)
);

CREATE TABLE bss.subscription (
    subscription_id VARCHAR(20) NOT NULL,
    subscriber_id VARCHAR(20),
    product_code VARCHAR(12),
    start_date DATE,
    end_date DATE,
    monthly_fee DECIMAL(12,2),
    PRIMARY KEY (subscription_id)
);

CREATE TABLE bss.product_catalog (
    product_code VARCHAR(12) NOT NULL,
    product_name VARCHAR(100),
    product_family VARCHAR(30),
    list_price DECIMAL(12,2),
    PRIMARY KEY (product_code)
);

CREATE TABLE usage.daily_usage_summary (
    subscriber_id VARCHAR(20) NOT NULL,
    usage_date DATE NOT NULL,
    data_mb DECIMAL(14,2),
    voice_min DECIMAL(10,2),
    PRIMARY KEY (subscriber_id, usage_date)
);

CREATE TABLE crm.churn_event (
    subscriber_id VARCHAR(20) NOT NULL,
    churn_date DATE,
    churn_reason VARCHAR(40),
    PRIMARY KEY (subscriber_id)
);
