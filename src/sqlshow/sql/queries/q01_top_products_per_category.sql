-- title: Top 3 products per category
-- question: Which three products earn the most in each leaf category?
-- technique: ROW_NUMBER() over a partition, filtered in an outer query
--
-- A window function cannot be used in WHERE, so the ranking is computed in one CTE and filtered in the next.
-- ROW_NUMBER (and not RANK) gives exactly three rows per category; product_id breaks ties so the answer is stable.
WITH product_revenue AS (
    SELECT category_id, product_id, SUM(amount) AS revenue
    FROM sales
    GROUP BY category_id, product_id
),
ranked AS (
    SELECT category_id, product_id, revenue,
           ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY revenue DESC, product_id) AS rank
    FROM product_revenue
)
SELECT category_id, rank, product_id, revenue
FROM ranked
WHERE rank <= 3
ORDER BY category_id, rank;
