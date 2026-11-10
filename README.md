# sqlshow: PostgreSQL analytics, checked and measured

[![CI](https://github.com/TexAlphaWolf/ana-sql-showcase/actions/workflows/ci.yml/badge.svg)](https://github.com/TexAlphaWolf/ana-sql-showcase/actions/workflows/ci.yml)
[![CodeQL](https://github.com/TexAlphaWolf/ana-sql-showcase/actions/workflows/codeql.yml/badge.svg)](https://github.com/TexAlphaWolf/ana-sql-showcase/actions/workflows/codeql.yml)
![Python 3.11-3.14](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)
![PostgreSQL 16-18](https://img.shields.io/badge/PostgreSQL-16%E2%80%9318-336791)
![License MIT](https://img.shields.io/badge/license-MIT-green)

Thirteen commented analytical queries on a small online shop (window functions, recursive CTEs, gaps and islands,
LATERAL, ROLLUP and more), each **checked against an independent computation in Python**, and ten index experiments,
each **measured with `EXPLAIN (ANALYZE, BUFFERS)`** before and after. It is a command-line tool (`sqlshow`) with tests,
a Docker Compose setup and a report generated from the measured numbers.

![Summary of the full run](docs/summary.png)

## What the numbers say

All figures are from one run on PostgreSQL 18.6 in Docker ([`docs/report.json`](docs/report.json), scale 1: 200,000
orders, 437,300 order lines, 550,513 events; 45 s; median of 5 runs, warm cache, JIT off).

1. **The thirteen queries take 151 to 672 ms**, all reading whole tables (a sequential scan on the baseline schema,
   which has primary keys only). That is the nature of analytics: a report that needs every order does not get faster
   with an index on a customer.
2. **An index pays when a query needs a few rows of a big table.** An expression index on `lower(email)` turned
   3.51 ms into 0.01 ms (**292.4x**), a partial index on pending orders 7.59 ms into 0.11 ms (**69.0x**), an index on
   the foreign key `orders.customer_id` 4.04 ms into 0.12 ms (**34.8x**).
3. **The size of the gain follows how much of the table the query needs, not the kind of index.** GIN on a JSONB
   column gave 17.4x for one campaign (0.5% of the events, scattered through the table); a covering index, whose query already used an index, gave 2.7x.
4. **A cheaper index can be enough.** On the same query, a BRIN index of 24.0 KiB gave 5.2x and a B-tree of 4.3 MiB gave
   15.1x: the B-tree is 184 times larger and three times faster.
5. **Not every index helps much.** On a `NOT EXISTS` over all orders, the index was used and the gain was 1.3x
   (30.6 ms to 22.8 ms).

[`docs/analysis.md`](docs/analysis.md) goes through each result; [`docs/evaluation.md`](docs/evaluation.md) is the
full generated report, with the plan of every query.

## Quick start

With Docker (PostgreSQL 18 and the tool, nothing else to install):

```bash
docker compose up -d --wait db
docker compose run --rm sqlshow init --scale 1        # builds the schema "sqlshow" and loads the data
docker compose run --rm sqlshow queries               # lists the thirteen queries
docker compose run --rm sqlshow run --only q07        # runs one and prints its result
docker compose run --rm sqlshow evaluate --out /out   # every query and every experiment, with the report
docker compose down -v
```

On Windows, `tools\run_full.ps1` does all of it and leaves the report in `results\`. Without Docker, with Python 3.11 or
later and a PostgreSQL 16 or later you can write to:

```bash
pip install git+https://github.com/TexAlphaWolf/ana-sql-showcase.git
export SQLSHOW_DSN=postgresql://user:password@localhost:5432/dbname
sqlshow init --scale 0.1     # drops and recreates ONLY the schema "sqlshow" in that database
sqlshow evaluate --out out
sqlshow render out/report.json -o out/evaluation.md --figure out/summary.png   # rebuild from the JSON
```

## The queries

Each file in [`src/sqlshow/sql/queries/`](src/sqlshow/sql/queries) starts with the question it answers and the technique
it shows. Times are the median on the baseline schema.

| Query | Technique | Median (ms) |
|---|---|---|
| q01 Top 3 products per category | ROW_NUMBER() over a partition | 325.5 |
| q02 Monthly revenue, growth and moving average | LAG, a named WINDOW, a ROWS frame | 341.7 |
| q03 Cohort retention | CTEs, DISTINCT, month arithmetic | 300.3 |
| q04 RFM customer segments | NTILE scores and CASE | 452.4 |
| q05 Pareto and ABC classes | running SUM and grand-total SUM | 160.4 |
| q06 Revenue up a category tree | two recursive CTEs | 151.1 |
| q07 Sessions from a click stream | LAG and a running SUM of flags | 665.2 |
| q08 Longest streaks of active days | gaps and islands | 291.9 |
| q09 Order value percentiles by country | PERCENTILE_CONT and FILTER | 422.0 |
| q10 Products bought together | a self-join with an inequality | 672.0 |
| q11 Last three orders of the top customers | CROSS JOIN LATERAL | 364.4 |
| q12 Revenue by year and country with subtotals | ROLLUP and GROUPING() | 601.2 |
| q13 Category of the first purchase | DISTINCT ON | 367.3 |

Revenue always means the lines of orders that are `paid` or `shipped`. The data is synthetic and generated from a seed,
with money in integer cents; [`docs/method.md`](docs/method.md) says what is in it and how it is checked.

## The index experiments

Each one measures a single query before and after an index, with everything else equal, checks that the result did not
change, and drops what it built.

| Experiment | Before (ms) | After (ms) | Speed-up | Index size |
|---|---|---|---|---|
| e01 Index on a foreign key | 4.04 | 0.12 | 34.8x | 1.8 MiB |
| e02 B-tree on a time range | 6.90 | 0.46 | 15.1x | 4.3 MiB |
| e03 BRIN on a time range | 6.44 | 1.25 | 5.2x | 24.0 KiB |
| e04 Composite index that also gives the order | 0.09 | 0.02 | 5.1x | 6.0 MiB |
| e05 Covering index and an index-only scan | 0.91 | 0.34 | 2.7x | 6.0 MiB |
| e06 Partial index | 7.59 | 0.11 | 69.0x | 40.0 KiB |
| e07 Expression index | 3.51 | 0.01 | 292.4x | 808.0 KiB |
| e08 GIN on a JSONB column | 37.6 | 2.17 | 17.4x | 1.0 MiB |
| e09 Index on the foreign key of a large table | 10.7 | 0.91 | 11.8x | 3.0 MiB |
| e10 An index that barely helps | 30.6 | 22.8 | 1.3x | 1.8 MiB |

The queries, the plans and the cost of building each index are in [`docs/evaluation.md`](docs/evaluation.md).

## Where this does not apply

- The data is synthetic and the tables fit in memory; the timings are of a warm cache. Differences grow with the size of
  the table, and a cold disk changes them.
- One machine, one PostgreSQL version, one run; the planner can choose differently elsewhere. The measurement is
  repeatable with `tools/run_full.ps1`, and the server settings are in the report.
- The cost of an index on writes is not measured, only its size and build time.

More in [`docs/limitations.md`](docs/limitations.md).

## Documentation

- [`docs/analysis.md`](docs/analysis.md): what the numbers show, experiment by experiment
- [`docs/method.md`](docs/method.md): the data, the checks and how the time is measured
- [`docs/architecture.md`](docs/architecture.md): modules and data flow
- [`docs/limitations.md`](docs/limitations.md): where the numbers can mislead
- [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), [`CHANGELOG.md`](CHANGELOG.md)

## License

MIT, Luca Tessitore.
