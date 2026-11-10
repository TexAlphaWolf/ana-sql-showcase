"""Connection, schema and loading. Everything lives in the schema "sqlshow"; nothing else in the database is touched."""

from __future__ import annotations

import os
from importlib import resources

import psycopg

from sqlshow import __version__
from sqlshow.datagen import Dataset, cents, generate, props_json, timestamp

SCHEMA = "sqlshow"
DSN_ENV = "SQLSHOW_DSN"


class ConfigError(Exception):
    """The user must fix something (no DSN, no data loaded); the CLI prints the message and exits with 2."""


def resolve_dsn(dsn: str | None) -> str:
    value = dsn or os.environ.get(DSN_ENV)
    if not value:
        raise ConfigError(
            f"no database given: pass --dsn or set {DSN_ENV}, for example "
            f"{DSN_ENV}=postgresql://user:password@localhost:5432/dbname"
        )
    return value


def connect(dsn: str | None) -> psycopg.Connection:
    """A connection that uses the schema, UTC and no JIT (so that timings do not include compilation)."""
    try:
        return psycopg.connect(
            resolve_dsn(dsn),
            autocommit=True,
            options=f"-c search_path={SCHEMA} -c timezone=UTC -c jit=off",
            connect_timeout=15,
        )
    except psycopg.OperationalError as exc:
        raise ConfigError(f"cannot connect to the database: {str(exc).strip()}") from exc


def read_sql(name: str) -> str:
    return resources.files("sqlshow").joinpath("sql", name).read_text(encoding="utf-8")


def create_schema(conn: psycopg.Connection) -> None:
    """Drop and rebuild the schema (and only it)."""
    conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    conn.execute(f"CREATE SCHEMA {SCHEMA}")
    conn.execute(read_sql("schema.sql"))


def load(conn: psycopg.Connection, data: Dataset) -> None:
    """Fill the tables with COPY and record how the data was made."""
    with conn.cursor() as cur:
        for table, columns, rows in (
            ("categories", "category_id, parent_id, name", data.categories),
            ("products", "product_id, category_id, name, price", ((a, b, c, cents(d)) for a, b, c, d in data.products)),
            ("customers", "customer_id, email, country, signed_up", data.customers),
            (
                "orders",
                "order_id, customer_id, ordered_at, status",
                ((a, b, timestamp(c), d) for a, b, c, d in data.orders),
            ),
            (
                "order_items",
                "order_id, line_no, product_id, quantity, unit_price",
                ((a, b, c, d, cents(e)) for a, b, c, d, e in data.order_items),
            ),
            (
                "events",
                "event_id, customer_id, occurred_at, kind, props",
                ((a, b, timestamp(c), d, props_json(e)) for a, b, c, d, e in data.events),
            ),
        ):
            with cur.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
        meta = {"scale": repr(data.scale), "seed": str(data.seed), "sqlshow": __version__}
        meta.update({f"rows_{name}": str(count) for name, count in data.counts().items()})
        cur.executemany("INSERT INTO meta (key, value) VALUES (%s, %s)", list(meta.items()))
    conn.execute("VACUUM ANALYZE")


def init(conn: psycopg.Connection, scale: float, seed: int) -> Dataset:
    data = generate(scale, seed)
    create_schema(conn)
    load(conn, data)
    return data


def meta(conn: psycopg.Connection) -> dict[str, str]:
    """What `init` recorded; raises ConfigError if the schema has not been loaded."""
    try:
        return dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except psycopg.errors.UndefinedTable as exc:
        raise ConfigError("the database has no data: run `sqlshow init` first") from exc


def server_info(conn: psycopg.Connection) -> dict[str, str]:
    """Version and the settings that decide how plans and timings come out."""
    version = conn.execute("SHOW server_version").fetchone()
    assert version is not None
    info = {"server_version": str(version[0])}
    for name in (
        "shared_buffers",
        "work_mem",
        "effective_cache_size",
        "random_page_cost",
        "max_parallel_workers_per_gather",
        "jit",
        "server_encoding",
    ):
        row = conn.execute("SELECT current_setting(%s)", (name,)).fetchone()
        assert row is not None
        info[name] = str(row[0])
    row = conn.execute("SELECT datcollate FROM pg_database WHERE datname = current_database()").fetchone()
    info["collation"] = str(row[0]) if row and row[0] else "n/a"
    return info


def table_sizes(conn: psycopg.Connection) -> dict[str, int]:
    """Bytes of each table with its indexes."""
    rows = conn.execute(
        "SELECT c.relname, pg_total_relation_size(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind = 'r' ORDER BY c.relname",
        (SCHEMA,),
    ).fetchall()
    return {str(name): int(size) for name, size in rows}
