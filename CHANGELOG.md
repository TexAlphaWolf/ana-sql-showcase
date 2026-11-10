# Changelog

## 1.0.0

First release.

- Thirteen commented PostgreSQL queries (window functions, recursive CTEs, gaps and islands, LATERAL, ROLLUP,
  DISTINCT ON and more), each checked against an independent computation in Python.
- Ten index experiments measured with EXPLAIN ANALYZE (B-tree, BRIN, GIN, composite, covering, partial and expression
  indexes, and one that barely helps).
- Synthetic data from a seed; `sqlshow init`, `queries`, `run`, `bench`, `evaluate`, `render`.
- Docker Compose with PostgreSQL 18; CI on PostgreSQL 16, 17 and 18.
