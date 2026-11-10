# Architecture

```
datagen.py ──> Dataset (plain tuples) ──> db.py (schema.sql, COPY) ──> PostgreSQL, schema "sqlshow"
                    │                                                        │
                    └── tests/reference.py (answers in Python)               ├── queries.py (sql/queries/*.sql, EXPLAIN)
                                                                             └── bench.py (index experiments)
                                          evaluate.py ──> report.json ──> report.py ──> evaluation.md, summary.png
```

| Module | What it does |
|---|---|
| `datagen.py` | Makes the rows of the shop from a seed: categories (a three-level tree), products, customers, orders, order lines and a click stream. Money is integer cents and times are integer seconds until they reach the database. |
| `db.py` | Connects (UTC, no JIT, `search_path = sqlshow`), rebuilds the schema `sqlshow` (and only it), loads with `COPY`, records how the data was made in a `meta` table, reads the server settings. |
| `queries.py` | Finds the query files and reads their headers (title, question, technique); runs a query, hashes its result, and measures it with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. |
| `bench.py` | The ten index experiments: baseline, build the index, measure again, compare the results (an index must never change them), and drop what was built, even on failure. |
| `evaluate.py` | Checks that the schema is the baseline (primary keys only), runs everything and returns one dictionary. |
| `report.py` | Markdown and a figure, from the dictionary alone. |
| `cli.py` | `init`, `queries`, `run`, `bench`, `evaluate`, `render`. |

## The schema

Six tables (`categories`, `products`, `customers`, `orders`, `order_items`, `events`), a view `sales` (the order lines of
paid or shipped orders, which is what "revenue" means in every query) and a `meta` table. Only primary keys are declared,
on purpose: PostgreSQL does not index a foreign key, and the experiments start from that baseline.

Order ids and event ids follow time, as they do in a real system that numbers rows as they arrive. That matters for
BRIN indexes, which only work when the physical order of the rows follows the column.

## What the tests check

- `tests/reference.py` computes the answer of every query from the generated rows, in plain Python, and
  `tests/test_queries.py` compares the two. The comparison is run on three different data sets in CI.
- The experiments leave no index behind, refuse an index that changes a result, and clean up when a query fails.
- The generator is repeatable, and its rows satisfy the invariants the queries rely on.
- `tests/test_docs.py` compares every number in the README with `docs/report.json`.
