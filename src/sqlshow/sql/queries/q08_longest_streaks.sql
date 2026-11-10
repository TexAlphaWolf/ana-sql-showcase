-- title: Longest streaks of active days
-- question: Which customers were active on the most consecutive days?
-- technique: gaps and islands (date minus ROW_NUMBER is constant inside a run of consecutive days)
--
-- For consecutive days, the day advances by one and so does the row number, so their difference stays the same: that
-- difference names the "island". Counting the days of each island gives the streak length.
WITH active_days AS (
    SELECT DISTINCT customer_id, occurred_at::date AS day
    FROM events
),
numbered AS (
    SELECT customer_id, day,
           day - (ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY day))::int AS island
    FROM active_days
),
streaks AS (
    SELECT customer_id, MIN(day) AS first_day, MAX(day) AS last_day, COUNT(*) AS days
    FROM numbered
    GROUP BY customer_id, island
),
best AS (
    SELECT customer_id, first_day, last_day, days,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY days DESC, first_day) AS rn
    FROM streaks
)
SELECT customer_id, days AS streak_days, first_day, last_day
FROM best
WHERE rn = 1
ORDER BY days DESC, first_day, customer_id
LIMIT 10;
