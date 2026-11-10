-- title: Last three orders of the top customers
-- question: For the five biggest customers, what were their three most recent orders?
-- technique: CROSS JOIN LATERAL, the "top N per group" that can use an index
--
-- A LATERAL subquery may refer to the row of the table on its left, so it runs once per customer with its own ORDER BY
-- and LIMIT. This is the standard way to get the last N rows of each group.
WITH top_customers AS (
    SELECT customer_id, SUM(amount) AS revenue
    FROM sales
    GROUP BY customer_id
    ORDER BY revenue DESC, customer_id
    LIMIT 5
)
SELECT t.customer_id,
       l.rn,
       l.order_id,
       l.ordered_at,
       l.total
FROM top_customers AS t
CROSS JOIN LATERAL (
    SELECT o.order_id,
           o.ordered_at,
           SUM(oi.quantity * oi.unit_price) AS total,
           ROW_NUMBER() OVER (ORDER BY o.ordered_at DESC, o.order_id DESC) AS rn
    FROM orders AS o
    JOIN order_items AS oi USING (order_id)
    WHERE o.customer_id = t.customer_id AND o.status IN ('paid', 'shipped')
    GROUP BY o.order_id, o.ordered_at
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 3
) AS l
ORDER BY t.revenue DESC, t.customer_id, l.rn;
