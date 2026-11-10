"""The full evaluation: every query and every index experiment on the loaded data, as one JSON-able report."""

from __future__ import annotations

import platform
import time
from collections.abc import Callable
from importlib import metadata
from typing import Any

import psycopg

from sqlshow import __version__, bench, db, queries


def check_baseline(conn: psycopg.Connection) -> None:
    """The measurements start from primary keys only: refuse to run on a schema that has other indexes."""
    rows = conn.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND indexname NOT LIKE %s ORDER BY indexname",
        (db.SCHEMA, "%_pkey"),
    ).fetchall()
    if rows:
        names = ", ".join(str(r[0]) for r in rows)
        raise db.ConfigError(f"the schema has indexes that are not primary keys ({names}): run `sqlshow init` again")


def table_rows(conn: psycopg.Connection) -> dict[str, int]:
    out = {}
    for name in db.table_sizes(conn):
        if name == "meta":
            continue
        row = conn.execute(f"SELECT count(*) FROM {name}").fetchone()  # name comes from the catalog
        assert row is not None
        out[name] = int(row[0])
    return out


def run_queries(
    conn: psycopg.Connection, repeat: int, progress: Callable[[str], None] | None = None
) -> list[dict[str, Any]]:
    out = []
    for q in queries.load_queries():
        if progress:
            progress(f"query {q.id}: {q.title}")
        rows = queries.fetch(conn, q.sql)
        t = queries.measure(conn, q.sql, repeat)
        out.append(
            {
                "id": q.id,
                "name": q.name,
                "title": q.title,
                "question": q.question,
                "technique": q.technique,
                "rows": len(rows),
                "result_sha256": queries.result_digest(rows),
                "median_ms": round(t.median_ms, 3),
                "min_ms": round(t.min_ms, 3),
                "max_ms": round(t.max_ms, 3),
                "planning_ms": round(t.planning_ms, 3),
                "root_node": t.root_node,
                "nodes": list(t.nodes),
                "shared_hit": t.shared_hit,
                "shared_read": t.shared_read,
            }
        )
    return out


def evaluate(
    conn: psycopg.Connection, repeat: int, command: str, progress: Callable[[str], None] | None = None
) -> dict[str, Any]:
    started = time.perf_counter()
    meta = db.meta(conn)
    check_baseline(conn)
    environment: dict[str, Any] = {
        "sqlshow": __version__,
        "python": platform.python_version(),
        "psycopg": metadata.version("psycopg"),
        "system": f"{platform.system()} {platform.machine()}",
        "server": db.server_info(conn),
        "scale": float(meta["scale"]),
        "seed": int(meta["seed"]),
        "repeat": repeat,
        "rows": table_rows(conn),
        "table_bytes": {k: v for k, v in db.table_sizes(conn).items() if k != "meta"},
        "command": command,
    }
    result = {
        "environment": environment,
        "queries": run_queries(conn, repeat, progress),
        "experiments": bench.run_all(conn, repeat, progress),
    }
    environment["seconds"] = round(time.perf_counter() - started, 1)
    return result
