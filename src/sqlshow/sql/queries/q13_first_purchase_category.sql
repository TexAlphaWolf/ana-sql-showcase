-- title: Category of the first purchase
-- question: Which categories bring customers in?
-- technique: DISTINCT ON, the first row of each group
--
-- DISTINCT ON (customer_id) keeps the first row of each customer in the ORDER BY: the earliest paid order, and the
-- lowest product id within it. It is PostgreSQL specific; ROW_NUMBER() = 1 is the portable form.
WITH first_lines AS (
    SELECT DISTINCT ON (customer_id) customer_id, product_id
    FROM sales
    ORDER BY customer_id, ordered_at, order_id, product_id
)
SELECT p.category_id,
       COUNT(*) AS customers
FROM first_lines AS f
JOIN products AS p USING (product_id)
GROUP BY p.category_id
ORDER BY customers DESC, p.category_id;
