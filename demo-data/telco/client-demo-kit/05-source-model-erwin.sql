-- Physical data model: Nimbus Mobile source systems (CRM, BSS, usage mediation)
-- Exported from the enterprise data-modelling tool (forward engineering, ANSI SQL target)
-- Fictional demo model. Generated for ADEF client demos.

-- Subscribers (owner: Customer Care Systems)
CREATE TABLE crm.subscriber (
    subscriber_id            VARCHAR(20)      NOT NULL,
    msisdn                   VARCHAR(15)     ,
    full_name                VARCHAR(200)    ,
    segment                  VARCHAR(20)     ,
    activation_date          DATE            ,
    status                   VARCHAR(12)     ,
    email_address            VARCHAR(200)     COMMENT 'Contact email',
    preferred_language       VARCHAR(5)       COMMENT 'ISO language code',
    created_by               VARCHAR(40)      COMMENT 'Audit user',
    CONSTRAINT pk_subscriber PRIMARY KEY (subscriber_id)
);

-- Product subscriptions (owner: BSS Platform Team)
CREATE TABLE bss.subscription (
    subscription_id          VARCHAR(20)      NOT NULL,
    subscriber_id            VARCHAR(20)     ,
    product_code             VARCHAR(12)     ,
    start_date               DATE            ,
    end_date                 DATE            ,
    monthly_fee              DECIMAL(12,2)   ,
    contract_term_months     INTEGER          COMMENT 'Commitment term',
    sales_channel            VARCHAR(20)      COMMENT 'Retail, online or telesales',
    CONSTRAINT pk_subscription PRIMARY KEY (subscription_id)
);

-- Product catalogue (owner: BSS Platform Team)
CREATE TABLE bss.product_catalog (
    product_code             VARCHAR(12)      NOT NULL,
    product_name             VARCHAR(100)    ,
    product_family           VARCHAR(30)     ,
    list_price               DECIMAL(12,2)   ,
    launch_date              DATE             COMMENT 'Product launch date',
    CONSTRAINT pk_product_catalog PRIMARY KEY (product_code)
);

-- Aggregated daily usage per subscriber (owner: Network Mediation)
CREATE TABLE usage.daily_usage_summary (
    subscriber_id            VARCHAR(20)      NOT NULL,
    usage_date               DATE             NOT NULL,
    data_mb                  DECIMAL(14,2)   ,
    voice_min                DECIMAL(10,2)   ,
    sms_count                INTEGER          COMMENT 'SMS sent',
    roaming_flag             BOOLEAN          COMMENT 'Any roaming usage that day',
    CONSTRAINT pk_daily_usage_summary PRIMARY KEY (subscriber_id, usage_date)
);

-- Port-out and disconnection events (owner: Customer Care Systems)
CREATE TABLE crm.churn_event (
    subscriber_id            VARCHAR(20)      NOT NULL,
    churn_date               DATE            ,
    churn_reason             VARCHAR(40)     ,
    win_back_offer_code      VARCHAR(12)      COMMENT 'Retention offer presented',
    CONSTRAINT pk_churn_event PRIMARY KEY (subscriber_id)
);

-- Relationships
ALTER TABLE bss.subscription ADD CONSTRAINT fk_subscription_subscriber_id FOREIGN KEY (subscriber_id) REFERENCES crm.subscriber (subscriber_id);
ALTER TABLE bss.subscription ADD CONSTRAINT fk_subscription_product_code FOREIGN KEY (product_code) REFERENCES bss.product_catalog (product_code);
ALTER TABLE usage.daily_usage_summary ADD CONSTRAINT fk_daily_usage_summary_subscriber_id FOREIGN KEY (subscriber_id) REFERENCES crm.subscriber (subscriber_id);
ALTER TABLE crm.churn_event ADD CONSTRAINT fk_churn_event_subscriber_id FOREIGN KEY (subscriber_id) REFERENCES crm.subscriber (subscriber_id);
