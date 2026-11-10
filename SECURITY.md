# Security

## Model

sqlshow is a command line program that **connects to a PostgreSQL database you name, creates and fills one schema in
it, and writes a report**. It opens no other connection, starts no service and runs no other program.

- **What it changes in the database:** `sqlshow init` runs `DROP SCHEMA IF EXISTS sqlshow CASCADE` and recreates it. It touches nothing outside
  that schema, but it **does drop that schema**: do not point it at a database where you keep a schema with that name.
  The experiments create indexes inside the schema and drop them again.
- **The SQL it runs** is in the package (`sql/schema.sql`, `sql/queries/*.sql`) and in `bench.py`; none of it is built
  from user input. The few literals in the experiment queries come from the database itself and are quoted with
  `psycopg.sql.Literal`. `--only` accepts ids from a fixed list.
- **Credentials:** the connection string comes from `--dsn` or `SQLSHOW_DSN`. Connection errors are printed without it.
  The password in `docker-compose.yml` (`sqlshow-demo`, overridable with `SQLSHOW_PASSWORD`) is for a throwaway database that is
  not published on any port.
- **The Docker image** runs as an unprivileged user and works with a read-only root filesystem (plus `--tmpfs /tmp`
  for matplotlib's cache) and no capabilities (see `docker-compose.yml`).
- **No real data** is in the repository or used by it: everything is generated from a seed.

## Reporting

If you find a vulnerability, please open a private security advisory on the GitHub repository (Security tab) rather
than a public issue.
