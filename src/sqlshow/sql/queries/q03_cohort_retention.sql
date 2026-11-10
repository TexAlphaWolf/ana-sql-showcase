-- title: Cohort retention
-- question: Of the customers who made their first purchase in a month, how many were still buying 0, 1, ... 11 months later?
-- technique: CTEs, DISTINCT, month arithmetic, and a percentage of a group total
--
-- A cohort is the month of the first paid order. "Active" means at least one paid order in that month.
WITH first_order AS (
    SELECT customer_id, date_trunc('month', MIN(ordered_at))::date AS cohort
    FROM orders
    WHERE status IN ('paid', 'shipped')
    GROUP BY customer_id
),
activity AS (
    SELECT DISTINCT customer_id, date_trunc('month', ordered_at)::date AS active_month
    FROM orders
    WHERE status IN ('paid', 'shipped')
),
cohort_size AS (
    SELECT cohort, COUNT(*) AS size FROM first_order GROUP BY cohort
),
offsets AS (
    SELECT f.cohort,
           ((EXTRACT(year FROM a.active_month) - EXTRACT(year FROM f.cohort)) * 12
            + EXTRACT(month FROM a.active_month) - EXTRACT(month FROM f.cohort))::int AS month_offset,
           f.customer_id
    FROM first_order AS f
    JOIN activity AS a USING (customer_id)
)
SELECT o.cohort,
       o.month_offset,
       COUNT(*) AS customers,
       s.size AS cohort_size,
       ROUND(100.0 * COUNT(*) / s.size, 2) AS retention_pct
FROM offsets AS o
JOIN cohort_size AS s ON s.cohort = o.cohort
WHERE o.month_offset BETWEEN 0 AND 11
GROUP BY o.cohort, o.month_offset, s.size
ORDER BY o.cohort, o.month_offset;
