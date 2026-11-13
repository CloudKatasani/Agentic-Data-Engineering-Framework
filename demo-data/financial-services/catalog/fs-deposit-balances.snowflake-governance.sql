-- Snowflake governance metadata for fs-deposit-balances (review; applying is A2, policies are A3)

CREATE TAG IF NOT EXISTS acme_customer_gold.CLASSIFICATION ALLOWED_VALUES 'public','internal','confidential','restricted';
CREATE MASKING POLICY IF NOT EXISTS acme_customer_gold.MASK_RESTRICTED AS (v VARCHAR) RETURNS VARCHAR ->
  CASE WHEN IS_ROLE_IN_SESSION('RESTRICTED_READER') THEN v ELSE '***MASKED***' END;

COMMENT ON TABLE acme_customer_gold.dim_customer IS 'Bank customer';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN customer_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN segment SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN kyc_status SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN full_name SET TAG acme_customer_gold.CLASSIFICATION = 'restricted';
-- ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN full_name SET MASKING POLICY acme_customer_gold.MASK_RESTRICTED;

COMMENT ON TABLE acme_customer_gold.dim_product IS 'Deposit product';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_code SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_name SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_type SET TAG acme_customer_gold.CLASSIFICATION = 'internal';

COMMENT ON TABLE acme_customer_gold.dim_account IS 'Deposit account';
ALTER TABLE acme_customer_gold.dim_account MODIFY COLUMN account_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_account MODIFY COLUMN customer_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_account MODIFY COLUMN product_code SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_account MODIFY COLUMN branch_code SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_account MODIFY COLUMN status SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_account MODIFY COLUMN currency SET TAG acme_customer_gold.CLASSIFICATION = 'internal';

COMMENT ON TABLE acme_customer_gold.fct_daily_balance IS 'End-of-day deposit balance';
ALTER TABLE acme_customer_gold.fct_daily_balance MODIFY COLUMN daily_balance_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_daily_balance MODIFY COLUMN account_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_daily_balance MODIFY COLUMN balance_date SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_daily_balance MODIFY COLUMN ledger_balance SET TAG acme_customer_gold.CLASSIFICATION = 'confidential';
ALTER TABLE acme_customer_gold.fct_daily_balance MODIFY COLUMN available_balance SET TAG acme_customer_gold.CLASSIFICATION = 'confidential';
