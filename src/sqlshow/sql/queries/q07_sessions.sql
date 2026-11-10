-- title: Sessions from a click stream
-- question: Group each customer's events into visits; which visits were the longest?
-- technique: LAG to find gaps, a running SUM of flags to number the groups
--
-- A new session starts at a customer's first event, or after a gap of more than 30 minutes (a gap of exactly 30
-- minutes continues the session). Summing the "new session" flags along the customer's timeline numbers the sessions.
-- event_id breaks ties between events with the same timestamp.
WITH ordered AS (
    SELECT customer_id, event_id, occurred_at,
           LAG(occurred_at) OVER (PARTITION BY customer_id ORDER BY occurred_at, event_id) AS previous_at
    FROM events
),
flagged AS (
    SELECT customer_id, event_id, occurred_at,
           CASE WHEN previous_at IS NULL OR occurred_at - previous_at > INTERVAL '30 minutes' THEN 1 ELSE 0 END AS new_session
    FROM ordered
),
numbered AS (
    SELECT customer_id, event_id, occurred_at,
           SUM(new_session) OVER (PARTITION BY customer_id ORDER BY occurred_at, event_id
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_no
    FROM flagged
)
SELECT customer_id,
       session_no,
       MIN(occurred_at) AS started_at,
       MAX(occurred_at) AS ended_at,
       COUNT(*) AS events,
       EXTRACT(EPOCH FROM MAX(occurred_at) - MIN(occurred_at))::int AS duration_seconds
FROM numbered
GROUP BY customer_id, session_no
ORDER BY events DESC, started_at, customer_id
LIMIT 20;
