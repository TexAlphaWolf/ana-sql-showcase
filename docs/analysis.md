# What the numbers show

Every figure is in [`report.json`](report.json) (one run: PostgreSQL 18.6 in Docker, scale 1, seed 1, 45 s, median of 5
executions after a warm-up) and in the generated [`evaluation.md`](evaluation.md); `tests/test_docs.py` checks the ones
quoted in the README. Server settings: `shared_buffers = 512MB`, `effective_cache_size = 2GB`, `random_page_cost = 1.1`,
`work_mem = 4MB`, two parallel workers per gather, JIT off.

## 1. The thirteen queries

They take between 151 ms (q06, the category tree) and 672 ms (q10, the product pairs), and every one reads the tables it
needs in full: the plans start with a sequential scan, and nothing was read from disk (`shared_read` is 0 everywhere).
So the time is CPU and memory: sorting for the window functions (q01, q04, q07, q08), hashing for the joins, and the
sort of 550,513 events by customer and time in q07.

The three slowest are q10 (672 ms), q07 (665 ms) and q12 (601 ms). q10 joins the order lines with themselves, q07 sorts
the largest table, q12 aggregates every revenue line by year and country. A report over everything is a cost of reading
everything; the indexes below do not target these queries, and the report does not claim they would help.

q11 touches 69,124 buffers against 4,143 to 11,136 for most of the others, and still takes 364 ms: it finds the top five
customers first and then looks up their last orders, and that second step repeats an index scan on `order_items_pkey`.
The buffer count is a useful second number next to the time, not a substitute.

## 2. Selectivity decides

| Experiment | Rows returned | Before (ms) | After (ms) | Speed-up |
|---|---|---|---|---|
| e07 e-mail lookup, 1 of 20,000 customers | 1 | 3.51 | 0.01 | 292.4x |
| e06 pending orders, 818 of 200,000 | 818 | 7.59 | 0.11 | 69.0x |
| e01 one customer's orders | 180 | 4.04 | 0.12 | 34.8x |
| e08 one campaign in a JSONB column, 0.5% of events | 1 (a count) | 37.6 | 2.17 | 17.4x |
| e02 one week of three years, B-tree | 7 (days) | 6.90 | 0.46 | 15.1x |
| e09 one product's order lines | 1 (a sum) | 10.7 | 0.91 | 11.8x |

The pattern is the share of the table the query needs: a customer out of 20,000, a status that 0.4% of orders have, a
week out of three years. The better the index discards, the larger the gain. Two things the table hides:

- e08 matches 2,731 events (0.5% of 550,513), scattered over the whole table, so the index still has to visit many
  pages (2,248 buffers against 6,225 for the scan); 17.4x is what a less selective condition gives.
- e09 reads 1,377 buffers with the index against 2,786 without it, only half, yet takes 12 times less time. The
  sequential scan also tests the condition on each of the 437,300 lines; the bitmap scan tests only the matching ones.
  Counting buffers alone would understate this gain.

## 3. BRIN against B-tree (e02 and e03)

The same query, a week of orders. The B-tree is 4.3 MiB and takes the query from 6.90 ms to 0.46 ms (15.1x), as an
index-only scan. The BRIN index is 24.0 KiB, 184 times smaller, builds in 17 ms against 55 ms, and gives 6.44 ms to
1.25 ms (5.2x). It works because the order ids follow time, so the rows of a week sit together in the table; on data
stored in another order a BRIN index would help much less. That case is not measured here.

## 4. The two small ratios (e04 and e05)

e04 goes from 0.09 ms to 0.02 ms (5.1x) and e05 from 0.91 ms to 0.34 ms (2.7x). Both started from an index on
`customer_id`, so they compare a good index with a better one. In absolute terms e04 saves 70 microseconds. What it buys
is that the cost no longer grows with the number of orders of a customer: 7 buffers against 175 for the customer used. The
covering index of e05 reads 18 buffers instead of 1,233 because the table is not visited at all; that needs the
visibility map to be current, which is why the experiment runs `VACUUM` first.

Ratios of two very small times are fragile. The "after" of e07 was 0.012 ms, between 0.007 and 0.018 ms over the five
runs, so 292.4x could as well be 200x or 500x on another run; the order of magnitude is the result, not the digits.

## 5. The index that barely helps (e10)

Customers with no orders, as a `NOT EXISTS`: the plan has to read the customer of every one of 200,000 orders whether or
not there is an index. With the index it did so as an index-only scan on a smaller structure (384 buffers against 1,448)
and went from 30.6 ms to 22.8 ms, 1.3x. It is the control of the set: an index is a choice for the planner and
pays only if it lets the query skip work.

## 6. What an index costs

Building took 17 to 113 ms and the indexes are 24.0 KiB to 6.0 MiB. The two multi-column indexes (e04, e05) are 6.0 MiB,
41% of the 14.7 MiB orders table, for a gain that matters only if that query is frequent. The slowdown of writes is not
measured; every index adds work to each insert and update.
