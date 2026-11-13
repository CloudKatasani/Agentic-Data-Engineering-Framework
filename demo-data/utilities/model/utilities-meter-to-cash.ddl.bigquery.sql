-- ADEF physical DDL | model utilities-meter-to-cash v1.0.0 | dialect BigQuery
-- Generated 2026-11-01T00:00:00+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS ACME_CUSTOMER_GOLD;

-- Customer Account (dimension, history: type2) grain: one row per customer account version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_GOLD.DIM_CUSTOMER_ACCOUNT (
    CUSTOMER_ACCOUNT_SK INT64 NOT NULL OPTIONS(description='Surrogate key / history column (type 2)'),
    VALID_FROM TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    VALID_TO TIMESTAMP OPTIONS(description='Surrogate key / history column (type 2)'),
    IS_CURRENT BOOL OPTIONS(description='Surrogate key / history column (type 2)'),
    CUSTOMER_ACCOUNT_ID STRING NOT NULL OPTIONS(description='Business key of the account'),
    ACCOUNT_STATUS STRING OPTIONS(description='A=active, I=inactive, C=closed'),
    RATE_CLASS STRING OPTIONS(description='Tariff rate class'),
    CUSTOMER_NAME STRING OPTIONS(description='Account holder name (masked for consumers)'),
    OPEN_DATE DATE OPTIONS(description='Account open date'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

-- Premise (dimension, history: type1) grain: one row per premise
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_GOLD.DIM_PREMISE (
    PREMISE_ID STRING NOT NULL OPTIONS(description='Business key of the premise'),
    CUSTOMER_ACCOUNT_ID STRING OPTIONS(description='Owning account'),
    PREMISE_TYPE STRING OPTIONS(description='Residential, commercial, industrial'),
    REGION_CODE STRING OPTIONS(description='Operating region'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

-- Meter (dimension, history: type1) grain: one row per meter
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_GOLD.DIM_METER (
    METER_ID STRING NOT NULL OPTIONS(description='Business key of the meter'),
    PREMISE_ID STRING OPTIONS(description='Premise where installed'),
    METER_TYPE STRING OPTIONS(description='AMI or legacy'),
    INSTALL_DATE DATE OPTIONS(description='Installation date'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

-- Billed Consumption (fact, history: none) grain: one row per final bill
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_GOLD.FCT_BILLED_CONSUMPTION (
    BILL_ID STRING NOT NULL OPTIONS(description='Business key of the bill'),
    CUSTOMER_ACCOUNT_ID STRING OPTIONS(description='Billed account'),
    BILL_PERIOD_START DATE OPTIONS(description='First day of bill period'),
    BILL_PERIOD_END DATE OPTIONS(description='Last day of bill period'),
    BILLED_KWH NUMERIC(18,3) OPTIONS(description='kWh on the bill'),
    METERED_KWH NUMERIC(18,3) OPTIONS(description='Metered kWh in the bill period'),
    ESTIMATED_READ_SHARE NUMERIC(5,4) OPTIONS(description='Share of estimated reads'),
    VARIANCE_KWH NUMERIC(18,3) OPTIONS(description='Billed minus metered kWh'),
    AMOUNT_DUE NUMERIC(18,2) OPTIONS(description='Amount billed'),
    LOAD_TS TIMESTAMP OPTIONS(description='Audit column'),
    SOURCE_SYSTEM STRING OPTIONS(description='Audit column'),
    BATCH_ID STRING OPTIONS(description='Audit column')
);

