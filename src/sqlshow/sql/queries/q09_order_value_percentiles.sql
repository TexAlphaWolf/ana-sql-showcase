-- title: Order value percentiles by country
-- question: What is a typical order, and a large one, in each country? How many orders are refunded?
-- technique: ordered-set aggregates (PERCENTILE_CONT) and FILTER
--
-- The mean hides skew; the median and the 90th and 99th percentiles show it. PERCENTILE_CONT interpolates between
-- the two nearest orders. FILTER counts only the rows that satisfy a condition, without a CASE. Every order counts here,
-- whatever its status.
WITH order_value AS (
    SELECT o.order_id, o.customer_id, o.status, SUM(oi.quantity * oi.unit_price) AS value
    FROM orders AS o
    JOIN order_items AS oi USING (order_id)
    GROUP BY o.order_id, o.customer_id, o.status
)
SELECT c.country,
       COUNT(*) AS orders,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v.value)::numeric, 2) AS median,
       ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY v.value)::numeric, 2) AS p90,
       ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY v.value)::numeric, 2) AS p99,
       ROUND(100.0 * COUNT(*) FILTER (WHERE v.status = 'refunded') / COUNT(*), 2) AS refunded_pct
FROM order_value AS v
JOIN customers AS c USING (customer_id)
GROUP BY c.country
ORDER BY orders DESC, c.country;
