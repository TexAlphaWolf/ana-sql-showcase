# Method

## Data

Synthetic, from a seed (`sqlshow init --scale 1 --seed 1`): 20,000 customers, 2,000 products in 60 leaf categories,
200,000 orders and about 440,000 order lines, and about 550,000 click-stream events. The shape is chosen so that the queries have
something to find: a few customers order and visit a lot, later months have more orders, some orders are refunded or
cancelled, the last two weeks have pending orders, some product pairs are bought together, and some gaps between
events are exactly 30 minutes (the session rule is tested at its boundary).

The numbers in the reports describe how PostgreSQL executes these queries on this data, never anything about real shops.

## What "revenue" means

An order line of an order whose status is `paid` or `shipped`. Refunded, cancelled and pending orders are not revenue.
Queries that need every order (q09) say so.

## Correctness

Each query has a reference in `tests/reference.py`: the same question answered from the generated rows, with no SQL.
Rounding follows the query (half away from zero, like PostgreSQL's `ROUND` on `numeric`); the percentiles of q09 are
floating point and are compared within a cent. Results are compared as sets of rows where the order depends on the
database's text collation, and in order where the query orders by numbers.

## Timing

- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, so the time is the server's execution time, without the network.
- One warm-up execution, then N (default 5) measured ones; the **median** is reported, with the minimum and maximum
  in `report.json`. The cache is warm: these are timings of CPU and memory, not of a cold disk.
- `jit = off` for the session, so that a timing does not include compilation.
- The server settings that decide plans (`shared_buffers`, `work_mem`, `effective_cache_size`, `random_page_cost`,
  parallel workers) are read from the server and printed in the report. `docker-compose.yml` sets three of them:
  `shared_buffers = 512MB`, `effective_cache_size = 2GB`, `random_page_cost = 1.1` (a machine with an SSD).
- Before each measurement the tables are `VACUUM ANALYZE`d.

## Index experiments

Each experiment: drop what it may have left, build the baseline (nothing, or a simpler index), `VACUUM ANALYZE`,
measure, build the index under test (the build time is recorded), `VACUUM ANALYZE`, measure again, and compare the two
results (they must be identical), report the size of the index, and drop everything. The query literals are chosen
from the data (a busy customer, a busy product, an existing e-mail) and written into the query with `psycopg.sql.Literal`.

The speed-up is `median before / median after`. The plan's node types are recorded so that the report says what the
planner did, not what the index was meant to do (e10 is there to show an index that barely helps: the planner uses it, but the gain is 1.3x, not 30x).
