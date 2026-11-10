# Evaluation

Run on Linux x86_64, Python 3.14.10, psycopg 3.3.8, PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2); scale 1, seed 1; 45 s; each timing is the median of 5 executions after one warm-up (EXPLAIN ANALYZE, JIT off); command `evaluate --repeat 5 --out /out`.

## 1. The data

| Table | Rows | Size with indexes |
|---|---|---|
| categories | 85 | 64.0 KiB |
| customers | 20,000 | 1.7 MiB |
| events | 550,513 | 60.6 MiB |
| order_items | 437,300 | 31.3 MiB |
| orders | 200,000 | 14.7 MiB |
| products | 2,000 | 224.0 KiB |

Server settings: shared_buffers = 512MB, work_mem = 4MB, effective_cache_size = 2GB, random_page_cost = 1.1, max_parallel_workers_per_gather = 2, jit = off, server_encoding = UTF8, collation = en_US.utf8.

## 2. The queries

Run on the baseline schema (primary keys only). Each result is checked against an independent computation in Python by the tests; here the row count and a hash of the result are recorded.

| Query | Rows | Median (ms) | Planning (ms) | Buffers hit / read | Data read by |
|---|---|---|---|---|---|
| q01 Top 3 products per category | 180 | 325.5 | 0.34 | 4,143 / 0 | Seq Scan |
| q02 Monthly revenue, growth and moving average | 36 | 341.7 | 0.29 | 4,143 / 0 | Seq Scan |
| q03 Cohort retention | 366 | 300.3 | 0.18 | 2,656 / 0 | Seq Scan |
| q04 RFM customer segments | 6 | 452.4 | 0.32 | 4,143 / 0 | Seq Scan |
| q05 Pareto and ABC classes | 2,000 | 160.4 | 0.28 | 4,161 / 0 | Seq Scan |
| q06 Revenue up a category tree | 85 | 151.1 | 0.34 | 4,174 / 0 | Seq Scan |
| q07 Sessions from a click stream | 20 | 665.2 | 0.11 | 6,240 / 0 | Seq Scan |
| q08 Longest streaks of active days | 10 | 291.9 | 0.17 | 6,240 / 0 | Seq Scan |
| q09 Order value percentiles by country | 8 | 422.0 | 0.26 | 5,981 / 0 | Index Scan using orders_pkey, Index Scan using order_items_pkey, Seq Scan |
| q10 Products bought together | 15 | 672.0 | 0.40 | 11,136 / 0 | Seq Scan, Index Scan using order_items_pkey, Index Scan using orders_pkey |
| q11 Last three orders of the top customers | 15 | 364.4 | 0.43 | 69,124 / 0 | Seq Scan, Index Scan using order_items_pkey |
| q12 Revenue by year and country with subtotals | 28 | 601.2 | 0.39 | 5,996 / 0 | Index Scan using order_items_pkey, Index Scan using orders_pkey, Seq Scan |
| q13 Category of the first purchase | 60 | 367.3 | 0.25 | 4,158 / 0 | Seq Scan |

- **q01**: Which three products earn the most in each leaf category? *ROW_NUMBER() over a partition, filtered in an outer query.* Plan: Incremental Sort > Subquery Scan > WindowAgg > Sort > Aggregate > Hash Join.
- **q02**: How does revenue move month over month, and what is the trend once the noise is smoothed? *LAG, a named WINDOW, and a ROWS frame for a moving average.* Plan: WindowAgg > WindowAgg > Sort > Aggregate > Hash Join > Hash Join.
- **q03**: Of the customers who made their first purchase in a month, how many were still buying 0, 1, ... 11 months later? *CTEs, DISTINCT, month arithmetic, and a percentage of a group total.* Plan: Aggregate > Aggregate > Seq Scan > Sort > Hash Join > Aggregate.
- **q04**: Who are the best customers, and who is slipping away? *NTILE scores, a CASE over the scores, aggregation of the segments.* Plan: Sort > Aggregate > Subquery Scan > WindowAgg > Sort > WindowAgg.
- **q05**: How concentrated is revenue? Which products make the first 80%, the next 15%, the rest? *a running SUM and a grand-total SUM over the same query.* Plan: Subquery Scan > WindowAgg > WindowAgg > Sort > Aggregate > Gather.
- **q06**: What does each category earn, counting everything below it? *two recursive CTEs (a path and a closure) over a self-referencing table.* Plan: Sort > Recursive Union > Seq Scan > Hash Join > Seq Scan > Hash.
- **q07**: Group each customer's events into visits; which visits were the longest? *LAG to find gaps, a running SUM of flags to number the groups.* Plan: Limit > Sort > Aggregate > WindowAgg > WindowAgg > Sort.
- **q08**: Which customers were active on the most consecutive days? *gaps and islands (date minus ROW_NUMBER is constant inside a run of consecutive days).* Plan: Limit > Sort > Subquery Scan > WindowAgg > Sort > Subquery Scan.
- **q09**: What is a typical order, and a large one, in each country? How many orders are refunded? *ordered-set aggregates (PERCENTILE_CONT) and FILTER.* Plan: Sort > Aggregate > Sort > Hash Join > Aggregate > Merge Join.
- **q10**: Which pairs of products appear in the same order most often? *a self-join with an inequality, so each pair is counted once.* Plan: Limit > Aggregate > Gather > Aggregate > Seq Scan > Sort.
- **q11**: For the five biggest customers, what were their three most recent orders? *CROSS JOIN LATERAL, the "top N per group" that can use an index.* Plan: Incremental Sort > Nested Loop > Limit > Sort > Aggregate > Gather.
- **q12**: How do I get the detail, the total of each year and the grand total in a single query? *GROUP BY ROLLUP and GROUPING().* Plan: Sort > Aggregate > Sort > Hash Join > Hash Join > Merge Join.
- **q13**: Which categories bring customers in? *DISTINCT ON, the first row of each group.* Plan: Sort > Aggregate > Hash Join > Unique > Sort > Hash Join.

## 3. Index experiments

Each experiment measures one query before and after an index, with everything else equal, and drops what it built.

| Experiment | Before (ms) | After (ms) | Speed-up | Data read before | Data read after | Index size | Build (ms) |
|---|---|---|---|---|---|---|---|
| e01 Index on a foreign key | 4.04 | 0.12 | 34.8x | Seq Scan | Bitmap Heap Scan, Bitmap Index Scan using idx_orders_customer | 1.8 MiB | 81.3 |
| e02 B-tree on a time range | 6.90 | 0.46 | 15.1x | Seq Scan | Index Only Scan using idx_orders_time | 4.3 MiB | 55.2 |
| e03 BRIN on a time range | 6.44 | 1.25 | 5.2x | Seq Scan | Bitmap Heap Scan, Bitmap Index Scan using idx_orders_time_brin | 24.0 KiB | 17.2 |
| e04 Composite index that also gives the order | 0.09 | 0.02 | 5.1x | Bitmap Heap Scan, Bitmap Index Scan using idx_orders_customer | Index Scan using idx_orders_customer_time | 6.0 MiB | 72.7 |
| e05 Covering index and an index-only scan | 0.91 | 0.34 | 2.7x | Bitmap Heap Scan, Bitmap Index Scan using idx_orders_customer | Index Only Scan using idx_orders_customer_status | 6.0 MiB | 96.3 |
| e06 Partial index | 7.59 | 0.11 | 69.0x | Seq Scan | Bitmap Heap Scan, Bitmap Index Scan using idx_orders_pending | 40.0 KiB | 20.6 |
| e07 Expression index | 3.51 | 0.01 | 292.4x | Seq Scan | Index Scan using idx_customers_email | 808.0 KiB | 45.8 |
| e08 GIN on a JSONB column | 37.6 | 2.17 | 17.4x | Seq Scan | Bitmap Heap Scan, Bitmap Index Scan using idx_events_props | 1.0 MiB | 99.6 |
| e09 Index on the foreign key of a large table | 10.7 | 0.91 | 11.8x | Seq Scan | Bitmap Heap Scan, Bitmap Index Scan using idx_items_product | 3.0 MiB | 112.7 |
| e10 An index that barely helps | 30.6 | 22.8 | 1.3x | Seq Scan | Index Only Scan using idx_orders_customer, Seq Scan | 1.8 MiB | 52.4 |

### e01 Index on a foreign key

PostgreSQL does not index a foreign key by itself. Without an index, finding one customer's orders reads the whole table.

```sql
SELECT order_id, ordered_at, status FROM orders WHERE customer_id = 13888
```

Before: no index. After: btree on customer_id (`CREATE INDEX idx_orders_customer ON orders (customer_id)`).

Rows returned: 180. Buffers hit / read: 1,291 / 0 before, 175 / 0 after.

### e02 B-tree on a time range

A week of orders out of three years: a range condition on a column that has no index.

```sql
SELECT date_trunc('day', ordered_at) AS day, count(*) FROM orders WHERE ordered_at >= '2025-06-01' AND ordered_at < '2025-06-08' GROUP BY 1 ORDER BY 1
```

Before: no index. After: btree on ordered_at (`CREATE INDEX idx_orders_time ON orders (ordered_at)`).

Rows returned: 7. Buffers hit / read: 1,329 / 0 before, 10 / 0 after.

### e03 BRIN on a time range

The same query as e02. Order ids follow time, so the rows of a week are stored together, and a BRIN index (one entry per block range) can find them at a tiny fraction of the size of a B-tree.

```sql
SELECT date_trunc('day', ordered_at) AS day, count(*) FROM orders WHERE ordered_at >= '2025-06-01' AND ordered_at < '2025-06-08' GROUP BY 1 ORDER BY 1
```

Before: no index. After: BRIN on ordered_at (`CREATE INDEX idx_orders_time_brin ON orders USING brin (ordered_at)`).

Rows returned: 7. Buffers hit / read: 1,329 / 0 before, 130 / 0 after.

### e04 Composite index that also gives the order

The last five orders of a customer. An index on customer_id finds the rows but they still have to be sorted; an index on (customer_id, ordered_at DESC) returns them already in order and stops after five.

```sql
SELECT order_id, ordered_at FROM orders WHERE customer_id = 13888 ORDER BY ordered_at DESC LIMIT 5
```

Before: btree on customer_id. After: btree on (customer_id, ordered_at DESC) (`DROP INDEX idx_orders_customer; CREATE INDEX idx_orders_customer_time ON orders (customer_id, ordered_at DESC)`).

Rows returned: 5. Buffers hit / read: 175 / 0 before, 7 / 0 after.

### e05 Covering index and an index-only scan

Counting the paid orders of a range of customers. If the index also holds the status column (INCLUDE), the table is not read at all, as long as the visibility map is up to date (hence the VACUUM).

```sql
SELECT count(*) FROM orders WHERE customer_id BETWEEN 5000 AND 5400 AND status = 'paid'
```

Before: btree on customer_id. After: btree on customer_id INCLUDE (status) (`DROP INDEX idx_orders_customer; CREATE INDEX idx_orders_customer_status ON orders (customer_id) INCLUDE (status)`).

Rows returned: 1. Buffers hit / read: 1,233 / 0 before, 18 / 0 after.

### e06 Partial index

Pending orders are a tiny part of the table and are looked up constantly. An index that holds only those rows is small and cheap to keep.

```sql
SELECT order_id, customer_id FROM orders WHERE status = 'pending'
```

Before: no index. After: partial btree WHERE status = 'pending' (`CREATE INDEX idx_orders_pending ON orders (customer_id) WHERE status = 'pending'`).

Rows returned: 818. Buffers hit / read: 1,291 / 0 before, 31 / 0 after.

### e07 Expression index

Case-insensitive lookup by e-mail. A plain index on email cannot serve lower(email) = ...; an index on the expression can.

```sql
SELECT customer_id, country FROM customers WHERE lower(email) = 'user10000@example.com'
```

Before: no index. After: btree on lower(email) (`CREATE INDEX idx_customers_email ON customers (lower(email))`).

Rows returned: 1. Buffers hit / read: 157 / 0 before, 3 / 0 after.

### e08 GIN on a JSONB column

Events of one campaign, found by containment (@>) on a JSONB document.

```sql
SELECT count(*) FROM events WHERE props @> '{"campaign": "c07"}'::jsonb
```

Before: no index. After: GIN (jsonb_path_ops) on props (`CREATE INDEX idx_events_props ON events USING gin (props jsonb_path_ops)`).

Rows returned: 1. Buffers hit / read: 6,225 / 0 before, 2,248 / 0 after.

### e09 Index on the foreign key of a large table

The revenue of one product, from the order lines (the biggest table of the shop).

```sql
SELECT sum(quantity * unit_price) AS revenue, count(*) AS lines FROM order_items WHERE product_id = 513
```

Before: no index. After: btree on product_id (`CREATE INDEX idx_items_product ON order_items (product_id)`).

Rows returned: 1. Buffers hit / read: 2,786 / 0 before, 1,377 / 0 after.

### e10 An index that barely helps

Customers with no orders, as a NOT EXISTS. The planner has to read the customer of every order either way, so an index on customer_id can only make that read cheaper, not skip it: the gain is small, unlike the other experiments.

```sql
SELECT count(*) FROM customers AS c WHERE NOT EXISTS (SELECT 1 FROM orders AS o WHERE o.customer_id = c.customer_id)
```

Before: no index. After: btree on customer_id (`CREATE INDEX idx_orders_customer ON orders (customer_id)`).

Rows returned: 1. Buffers hit / read: 1,448 / 0 before, 384 / 0 after.

