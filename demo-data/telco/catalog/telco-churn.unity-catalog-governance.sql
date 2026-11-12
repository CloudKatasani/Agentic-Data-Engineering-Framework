-- Unity Catalog governance metadata for telco-churn (review; applying is A2, grants are A3)

COMMENT ON TABLE main.acme_customer_gold.dim_subscriber IS 'Mobile subscriber';
ALTER TABLE main.acme_customer_gold.dim_subscriber SET TAGS ('adef_model' = 'telco-churn', 'grain' = 'one row per subscriber version');
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN subscriber_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN subscriber_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN segment COMMENT 'Consumer, SME or Enterprise';
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN segment SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN status COMMENT 'ACTIVE, SUSPENDED or CHURNED';
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN status SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN activation_date COMMENT 'Activation date';
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN activation_date SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN msisdn COMMENT 'Phone number (masked)';
ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN msisdn SET TAGS ('classification' = 'restricted');

COMMENT ON TABLE main.acme_customer_gold.dim_product IS 'Product offering';
ALTER TABLE main.acme_customer_gold.dim_product SET TAGS ('adef_model' = 'telco-churn', 'grain' = 'one row per product');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_code COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_code SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_name COMMENT 'Product name';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_name SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_family COMMENT 'Product family';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_family SET TAGS ('classification' = 'internal');

COMMENT ON TABLE main.acme_customer_gold.fct_subscription_month IS 'Monthly revenue, usage and churn per subscriber';
ALTER TABLE main.acme_customer_gold.fct_subscription_month SET TAGS ('adef_model' = 'telco-churn', 'grain' = 'one row per subscriber per month');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN subscription_month_id COMMENT 'Surrogate business key';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN subscription_month_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN subscriber_id COMMENT 'Subscriber';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN subscriber_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN product_code COMMENT 'Main product';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN product_code SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN month_start COMMENT 'Month';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN month_start SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN monthly_revenue COMMENT 'Revenue in month';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN monthly_revenue SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN data_mb COMMENT 'Data used';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN data_mb SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN voice_min COMMENT 'Voice minutes';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN voice_min SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN is_churned COMMENT 'Churned in month';
ALTER TABLE main.acme_customer_gold.fct_subscription_month ALTER COLUMN is_churned SET TAGS ('classification' = 'internal');

-- Column masks for Restricted attributes (A3: Security and Compliance approval required)
CREATE FUNCTION IF NOT EXISTS main.acme_customer_gold.mask_restricted(v STRING) RETURNS STRING RETURN CASE WHEN is_account_group_member('restricted_readers') THEN v ELSE '***' END;
-- ALTER TABLE main.acme_customer_gold.dim_subscriber ALTER COLUMN msisdn SET MASK main.acme_customer_gold.mask_restricted;
