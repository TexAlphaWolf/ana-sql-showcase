# Contributing

```bash
pip install -e ".[dev]"
docker run --rm -d -p 5432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:18
export SQLSHOW_TEST_DSN=postgresql://test:test@localhost:5432/test
ruff check . && ruff format --check . && mypy && pytest --cov
```

Without `SQLSHOW_TEST_DSN` the tests that need a database are skipped (the generator, the report and the CLI errors are
still tested). The tests rebuild the schema `sqlshow` of that database: use a throwaway one.
`SQLSHOW_TEST_SCALE` and `SQLSHOW_TEST_SEED` run the same tests on other data.

Rules that keep the project honest:

- **A new query needs a reference.** Add the file in `src/sqlshow/sql/queries/` (with the `title`, `question` and
  `technique` headers and a deterministic `ORDER BY`), its answer in `tests/reference.py`, and see the comparison pass on
  more than one seed. Queries must not need anything newer than PostgreSQL 15.
- **A new experiment must clean up** and must not change a result (the code checks both).
- **Numbers in the README come from `docs/report.json`**, and `tests/test_docs.py` checks them. After a new
  measurement (`tools/run_full.ps1`), copy the three files into `docs/` and update the text if a number moved.
