-- title: RFM customer segments
-- question: Who are the best customers, and who is slipping away?
-- technique: NTILE scores, a CASE over the scores, aggregation of the segments
--
-- Recency (days since the last paid order, at a fixed reference date), frequency (orders) and monetary value are each
-- cut into five equal groups; 5 is the best group on each. customer_id breaks ties so NTILE is reproducible.
WITH per_customer AS (
    SELECT customer_id,
           DATE '2026-01-01' - MAX(ordered_at)::date AS recency_days,
           COUNT(DISTINCT order_id) AS frequency,
           SUM(amount) AS monetary
    FROM sales
    GROUP BY customer_id
),
scored AS (
    SELECT customer_id, frequency, monetary,
           NTILE(5) OVER (ORDER BY recency_days DESC, customer_id) AS r,
           NTILE(5) OVER (ORDER BY frequency, customer_id) AS f,
           NTILE(5) OVER (ORDER BY monetary, customer_id) AS m
    FROM per_customer
)
SELECT CASE WHEN r >= 4 AND f >= 4 AND m >= 4 THEN 'champions'
            WHEN r >= 4 THEN 'recent'
            WHEN f >= 4 THEN 'loyal'
            WHEN r <= 2 AND m >= 4 THEN 'big spenders at risk'
            WHEN r <= 2 THEN 'at risk'
            ELSE 'regular'
       END AS segment,
       COUNT(*) AS customers,
       ROUND(AVG(monetary), 2) AS avg_monetary,
       ROUND(AVG(frequency), 2) AS avg_orders
FROM scored
GROUP BY 1
ORDER BY customers DESC, segment;
