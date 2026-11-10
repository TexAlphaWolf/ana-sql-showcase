-- title: Products bought together
-- question: Which pairs of products appear in the same order most often?
-- technique: a self-join with an inequality, so each pair is counted once
--
-- Joining order_items with itself on the order gives every pair of lines of an order; a.product_id < b.product_id keeps
-- (A, B) and drops (B, A) and (A, A). Support is the share of paid orders that contain the pair.
SELECT a.product_id AS product_a,
       b.product_id AS product_b,
       COUNT(*) AS orders_together,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM orders WHERE status IN ('paid', 'shipped')), 3) AS support_pct
FROM order_items AS a
JOIN order_items AS b ON b.order_id = a.order_id AND a.product_id < b.product_id
JOIN orders AS o ON o.order_id = a.order_id AND o.status IN ('paid', 'shipped')
GROUP BY a.product_id, b.product_id
ORDER BY orders_together DESC, product_a, product_b
LIMIT 15;
