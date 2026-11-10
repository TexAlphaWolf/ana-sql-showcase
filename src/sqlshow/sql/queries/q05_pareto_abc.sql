-- title: Pareto and ABC classes
-- question: How concentrated is revenue? Which products make the first 80%, the next 15%, the rest?
-- technique: a running SUM and a grand-total SUM over the same query
--
-- SUM() OVER () is the total of the whole result, SUM() OVER (ORDER BY ...) the running total. The frame is spelled
-- out as ROWS so that rows with equal revenue do not share a running total.
WITH product_revenue AS (
    SELECT product_id, SUM(amount) AS revenue
    FROM sales
    GROUP BY product_id
),
cumulative AS (
    SELECT product_id, revenue,
           SUM(revenue) OVER (ORDER BY revenue DESC, product_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running,
           SUM(revenue) OVER () AS total
    FROM product_revenue
)
SELECT product_id,
       revenue,
       ROUND(100 * running / total, 2) AS cumulative_pct,
       CASE WHEN running / total <= 0.80 THEN 'A'
            WHEN running / total <= 0.95 THEN 'B'
            ELSE 'C'
       END AS abc_class
FROM cumulative
ORDER BY revenue DESC, product_id;
