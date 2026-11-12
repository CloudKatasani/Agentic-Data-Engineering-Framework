-- Snowflake governance metadata for retail-sales (review; applying is A2, policies are A3)

CREATE TAG IF NOT EXISTS acme_customer_gold.CLASSIFICATION ALLOWED_VALUES 'public','internal','confidential','restricted';
CREATE MASKING POLICY IF NOT EXISTS acme_customer_gold.MASK_RESTRICTED AS (v VARCHAR) RETURNS VARCHAR ->
  CASE WHEN IS_ROLE_IN_SESSION('RESTRICTED_READER') THEN v ELSE '***MASKED***' END;

COMMENT ON TABLE acme_customer_gold.dim_store IS 'Physical store';
ALTER TABLE acme_customer_gold.dim_store MODIFY COLUMN store_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_store MODIFY COLUMN store_name SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_store MODIFY COLUMN region SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_store MODIFY COLUMN format SET TAG acme_customer_gold.CLASSIFICATION = 'internal';

COMMENT ON TABLE acme_customer_gold.dim_product IS 'Sellable product';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN product_name SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN category SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_product MODIFY COLUMN brand SET TAG acme_customer_gold.CLASSIFICATION = 'internal';

COMMENT ON TABLE acme_customer_gold.dim_customer IS 'Loyalty customer';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN customer_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN loyalty_tier SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN email SET TAG acme_customer_gold.CLASSIFICATION = 'restricted';
-- ALTER TABLE acme_customer_gold.dim_customer MODIFY COLUMN email SET MASKING POLICY acme_customer_gold.MASK_RESTRICTED;

COMMENT ON TABLE acme_customer_gold.fct_sales_line IS 'Store sales line';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN order_line_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN order_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN store_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN product_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN customer_id SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN order_date SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN quantity SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN net_amount SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
ALTER TABLE acme_customer_gold.fct_sales_line MODIFY COLUMN discount_amount SET TAG acme_customer_gold.CLASSIFICATION = 'internal';
