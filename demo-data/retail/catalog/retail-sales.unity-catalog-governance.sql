-- Unity Catalog governance metadata for retail-sales (review; applying is A2, grants are A3)

COMMENT ON TABLE main.acme_customer_gold.dim_store IS 'Physical store';
ALTER TABLE main.acme_customer_gold.dim_store SET TAGS ('adpe_model' = 'retail-sales', 'grain' = 'one row per store');
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN store_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN store_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN store_name COMMENT 'Store name';
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN store_name SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN region COMMENT 'Sales region';
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN region SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN format COMMENT 'FLAGSHIP, STANDARD or EXPRESS';
ALTER TABLE main.acme_customer_gold.dim_store ALTER COLUMN format SET TAGS ('classification' = 'internal');

COMMENT ON TABLE main.acme_customer_gold.dim_product IS 'Sellable product';
ALTER TABLE main.acme_customer_gold.dim_product SET TAGS ('adpe_model' = 'retail-sales', 'grain' = 'one row per product version');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_name COMMENT 'Product name';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN product_name SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN category COMMENT 'Category';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN category SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN brand COMMENT 'Brand';
ALTER TABLE main.acme_customer_gold.dim_product ALTER COLUMN brand SET TAGS ('classification' = 'internal');

COMMENT ON TABLE main.acme_customer_gold.dim_customer IS 'Loyalty customer';
ALTER TABLE main.acme_customer_gold.dim_customer SET TAGS ('adpe_model' = 'retail-sales', 'grain' = 'one row per loyalty customer');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN customer_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN customer_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN loyalty_tier COMMENT 'NONE, BRONZE, SILVER or GOLD';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN loyalty_tier SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN email COMMENT 'Email (masked)';
ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN email SET TAGS ('classification' = 'restricted');

COMMENT ON TABLE main.acme_customer_gold.fct_sales_line IS 'Store sales line';
ALTER TABLE main.acme_customer_gold.fct_sales_line SET TAGS ('adpe_model' = 'retail-sales', 'grain' = 'one row per order line');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN order_line_id COMMENT 'Business key';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN order_line_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN order_id COMMENT 'Order (basket)';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN order_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN store_id COMMENT 'Store';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN store_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN product_id COMMENT 'Product';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN product_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN customer_id COMMENT 'Loyalty customer (NONE if anonymous)';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN customer_id SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN order_date COMMENT 'Sales date';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN order_date SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN quantity COMMENT 'Units';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN quantity SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN net_amount COMMENT 'Net sales amount';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN net_amount SET TAGS ('classification' = 'internal');
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN discount_amount COMMENT 'Discount';
ALTER TABLE main.acme_customer_gold.fct_sales_line ALTER COLUMN discount_amount SET TAGS ('classification' = 'internal');

-- Column masks for Restricted attributes (A3: Security and Compliance approval required)
CREATE FUNCTION IF NOT EXISTS main.acme_customer_gold.mask_restricted(v STRING) RETURNS STRING RETURN CASE WHEN is_account_group_member('restricted_readers') THEN v ELSE '***' END;
-- ALTER TABLE main.acme_customer_gold.dim_customer ALTER COLUMN email SET MASK main.acme_customer_gold.mask_restricted;
