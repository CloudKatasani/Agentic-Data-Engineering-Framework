-- Unity Catalog governance metadata for fs-deposit-balances (review; applying is A2, grants are A3)

COMMENT ON TABLE main.acme_customer_gold.dim_customer IS 'Bank customer';
ALTER TABLE main.acme_customer_gold.dim_customer SET TAGS ('adef_model' = 'fs-deposit-balances', 'grain' = 'one row per customer version');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN customer_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN customer_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN segment COMMENT 'Mass, affluent or private';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN segment SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN kyc_status COMMENT 'VERIFIED, PENDING or EXPIRED';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN kyc_status SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN full_name COMMENT 'Customer name (masked)';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN full_name SET TAGS ('classification' = 'restricted');

COMMENT ON TABLE main.acme_customer_gold.dim_product IS 'Deposit product';
ALTER TABLE main.acme_customer_gold.dim_product SET TAGS ('adef_model' = 'fs-deposit-balances', 'grain' = 'one row per product');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_code COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_code SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_name COMMENT 'Product name';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_name SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_type COMMENT 'Current, savings or term';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_type SET TAGS ('classification' = 'internal');

COMMENT ON TABLE main.acme_customer_gold.dim_account IS 'Deposit account';
ALTER TABLE main.acme_customer_gold.dim_account SET TAGS ('adef_model' = 'fs-deposit-balances', 'grain' = 'one row per account version');
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN account_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN account_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN customer_id COMMENT 'Account holder';
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN customer_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN product_code COMMENT 'Product';
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN product_code SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN branch_code COMMENT 'Servicing branch';
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN branch_code SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN status COMMENT 'OPEN, DORMANT or CLOSED';
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN status SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN currency COMMENT 'ISO currency';
ALTER TABLE main.acme_customer_gold.dim_account ALTER COLUMN currency SET TAGS ('classification' = 'internal');

COMMENT ON TABLE main.acme_customer_gold.fct_daily_balance IS 'End-of-day deposit balance';
ALTER TABLE main.acme_customer_gold.fct_daily_balance SET TAGS ('adef_model' = 'fs-deposit-balances', 'grain' = 'one row per account per business day');
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN daily_balance_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN daily_balance_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN account_id COMMENT 'Account';
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN account_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN balance_date COMMENT 'Business date';
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN balance_date SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN ledger_balance COMMENT 'Ledger balance';
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN ledger_balance SET TAGS ('classification' = 'confidential');
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN available_balance COMMENT 'Available balance';
ALTER TABLE main.acme_customer_gold.fct_daily_balance ALTER COLUMN available_balance SET TAGS ('classification' = 'confidential');

-- Column masks for Restricted attributes (A3: Security and Compliance approval required)
CREATE FUNCTION IF NOT EXISTS main.acme_customer_gold.mask_restricted(v STRING) RETURNS STRING RETURN CASE WHEN is_account_group_member('restricted_readers') THEN v ELSE '***' END;
-- ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN full_name SET MASK main.acme_customer_gold.mask_restricted;
