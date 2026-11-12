-- ADPE physical DDL | model utilities-meter-to-cash v1.0.0 | dialect Databricks (Delta)
-- Generated 2026-11-12T19:20:16+00:00 from the approved logical model. Review before running (A2).

CREATE SCHEMA IF NOT EXISTS ACME_CUSTOMER_CURATED;

-- Customer Account (dimension, history: type2) grain: one row per customer account version
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_CUSTOMER_ACCOUNT (
    CUSTOMER_ACCOUNT_SK BIGINT NOT NULL COMMENT 'Surrogate key / history column (type 2)',
    VALID_FROM TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    VALID_TO TIMESTAMP COMMENT 'Surrogate key / history column (type 2)',
    IS_CURRENT BOOLEAN COMMENT 'Surrogate key / history column (type 2)',
    CUSTOMER_ACCOUNT_ID STRING NOT NULL COMMENT 'Business key of the account',
    ACCOUNT_STATUS STRING COMMENT 'A=active, I=inactive, C=closed',
    RATE_CLASS STRING COMMENT 'Tariff rate class',
    CUSTOMER_NAME STRING COMMENT 'Account holder name (masked for consumers)',
    OPEN_DATE DATE COMMENT 'Account open date',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Billing account of a customer';

-- Premise (dimension, history: type1) grain: one row per premise
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_PREMISE (
    PREMISE_ID STRING NOT NULL COMMENT 'Business key of the premise',
    CUSTOMER_ACCOUNT_ID STRING COMMENT 'Owning account',
    PREMISE_TYPE STRING COMMENT 'Residential, commercial, industrial',
    REGION_CODE STRING COMMENT 'Operating region',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Service location';

-- Meter (dimension, history: type1) grain: one row per meter
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.DIM_METER (
    METER_ID STRING NOT NULL COMMENT 'Business key of the meter',
    PREMISE_ID STRING COMMENT 'Premise where installed',
    METER_TYPE STRING COMMENT 'AMI or legacy',
    INSTALL_DATE DATE COMMENT 'Installation date',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Installed meter';

-- Billed Consumption (fact, history: none) grain: one row per final bill
CREATE TABLE IF NOT EXISTS ACME_CUSTOMER_CURATED.FCT_BILLED_CONSUMPTION (
    BILL_ID STRING NOT NULL COMMENT 'Business key of the bill',
    CUSTOMER_ACCOUNT_ID STRING COMMENT 'Billed account',
    BILL_PERIOD_START DATE COMMENT 'First day of bill period',
    BILL_PERIOD_END DATE COMMENT 'Last day of bill period',
    BILLED_KWH DECIMAL(18,3) COMMENT 'kWh on the bill',
    METERED_KWH DECIMAL(18,3) COMMENT 'Metered kWh in the bill period',
    ESTIMATED_READ_SHARE DECIMAL(5,4) COMMENT 'Share of estimated reads',
    VARIANCE_KWH DECIMAL(18,3) COMMENT 'Billed minus metered kWh',
    AMOUNT_DUE DECIMAL(18,2) COMMENT 'Amount billed',
    LOAD_TS TIMESTAMP COMMENT 'Audit column',
    SOURCE_SYSTEM STRING COMMENT 'Audit column',
    BATCH_ID STRING COMMENT 'Audit column'
) USING DELTA
COMMENT 'Billed versus metered consumption per bill';

ALTER TABLE ACME_CUSTOMER_CURATED.DIM_PREMISE ADD CONSTRAINT fk_premise_customer_account_id FOREIGN KEY (CUSTOMER_ACCOUNT_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_CUSTOMER_ACCOUNT (CUSTOMER_ACCOUNT_ID) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE ACME_CUSTOMER_CURATED.DIM_METER ADD CONSTRAINT fk_meter_premise_id FOREIGN KEY (PREMISE_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_PREMISE (PREMISE_ID) NOT ENFORCED; -- informational (not enforced)
ALTER TABLE ACME_CUSTOMER_CURATED.FCT_BILLED_CONSUMPTION ADD CONSTRAINT fk_billed_consumption_customer_account_id FOREIGN KEY (CUSTOMER_ACCOUNT_ID) REFERENCES ACME_CUSTOMER_CURATED.DIM_CUSTOMER_ACCOUNT (CUSTOMER_ACCOUNT_ID) NOT ENFORCED; -- informational (not enforced)
