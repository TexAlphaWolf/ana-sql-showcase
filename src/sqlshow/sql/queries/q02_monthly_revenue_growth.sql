-- title: Monthly revenue, growth and moving average
-- question: How does revenue move month over month, and what is the trend once the noise is smoothed?
-- technique: LAG, a named WINDOW, and a ROWS frame for a moving average
--
-- NULLIF turns a zero denominator into NULL instead of an error. The moving average is over the current month and
-- the two before it (a ROWS frame counts rows, and there is one row per month).
WITH monthly AS (
    SELECT date_trunc('month', ordered_at)::date AS month, SUM(amount) AS revenue
    FROM sales
    GROUP BY 1
)
SELECT month,
       revenue,
       LAG(revenue) OVER w AS previous,
       ROUND(100 * (revenue - LAG(revenue) OVER w) / NULLIF(LAG(revenue) OVER w, 0), 2) AS growth_pct,
       ROUND(AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_3m
FROM monthly
WINDOW w AS (ORDER BY month)
ORDER BY month;
