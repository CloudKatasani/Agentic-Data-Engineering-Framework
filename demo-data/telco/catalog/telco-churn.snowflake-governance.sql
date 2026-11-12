-- Snowflake governance metadata for telco-churn (review; applying is A2, policies are A3)

CREATE TAG IF NOT EXISTS acme_customer_gold.CLASSIFICATION ALLOWED_VALUES 'public','internal','confidential','restricted';
CREATE MASKING POLICY IF NOT EXISTS acme_customer_gold.MASK_RESTRICTED AS (v VARCHAR) RETURNS VARCHAR ->
  CASE WHEN IS_ROLE_IN_SESSION('RESTRICTED_READER') THEN v ELSE '***MASKED***' END;

COMMENT ON TABLE acme_customer_gold.dim_subscriber IS 'Mobile subscriber';
ALTER TABLE acme_customer_gold.dim_subscriber MODIFY COLUMN subscriber_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_subscriber MODIFY COLUMN segment SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_subscriber MODIFY COLUMN status SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_subscriber MODIFY COLUMN activation_date SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_subscriber MODIFY COLUMN msisdn SET TAG acme_customer_gold.CLASSIFICATION = 'restricted';
-- ALTER TABLE acme_customer_gold.dim_subscriber MODIFY COLUMN msisdn SET MASKING POLICY acme_customer_gold.MASK_RESTRICTED;

COMMENT ON TABLE acme_customer_gold.dim_product IS 'Product offering';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_code SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_name SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_family SET TAG acme_customer_gold.CLASSIFICATION = 'internal';

COMMENT ON TABLE acme_customer_gold.fct_subscription_month IS 'Monthly revenue, usage and churn per subscriber';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN subscription_month_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN subscriber_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN product_code SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN month_start SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN monthly_revenue SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN data_mb SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN voice_min SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_subscription_month MODIFY COLUMN is_churned SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
