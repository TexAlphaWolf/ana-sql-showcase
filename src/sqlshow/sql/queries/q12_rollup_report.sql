-- title: Revenue by year and country with subtotals
-- question: How do I get the detail, the total of each year and the grand total in a single query?
-- technique: GROUP BY ROLLUP and GROUPING()
--
-- ROLLUP (year, country) computes the groups (year, country), (year) and (). In the subtotal rows the grouped-away
-- columns are NULL; GROUPING() tells those NULLs from a real NULL: 0 detail, 1 country subtotal, 3 grand total.
SELECT s.year,
       c.country,
       SUM(s.amount) AS revenue,
       COUNT(DISTINCT s.order_id) AS orders,
       GROUPING(s.year, c.country) AS grouping_level
FROM (
    SELECT EXTRACT(year FROM ordered_at)::int AS year, customer_id, order_id, amount
    FROM sales
) AS s
JOIN customers AS c USING (customer_id)
GROUP BY ROLLUP (s.year, c.country)
ORDER BY s.year NULLS LAST, c.country NULLS LAST;
