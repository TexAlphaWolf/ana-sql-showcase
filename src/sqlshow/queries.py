"""The query files (sql/queries/*.sql): their headers, execution and plans."""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from importlib import resources
from typing import Any

import psycopg


@dataclass(frozen=True)
class Query:
    id: str  # q01 ...
    name: str  # file stem
    title: str
    question: str
    technique: str
    sql: str


@dataclass(frozen=True)
class Plan:
    """What EXPLAIN (ANALYZE, BUFFERS) said about one execution."""

    execution_ms: float
    planning_ms: float
    root_node: str
    nodes: tuple[str, ...]
    shared_hit: int
    shared_read: int


@dataclass(frozen=True)
class Timing:
    """The median of several executions, with the plan of the last one."""

    median_ms: float
    min_ms: float
    max_ms: float
    planning_ms: float
    root_node: str
    nodes: tuple[str, ...]
    shared_hit: int
    shared_read: int


def _header(sql: str, key: str) -> str:
    prefix = f"-- {key}:"
    for line in sql.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise ValueError(f"missing '{prefix}' header")


def load_queries() -> list[Query]:
    folder = resources.files("sqlshow").joinpath("sql", "queries")
    queries = []
    for item in sorted(folder.iterdir(), key=lambda p: p.name):
        if not item.name.endswith(".sql"):
            continue
        sql = item.read_text(encoding="utf-8")
        stem = item.name.removesuffix(".sql")
        queries.append(
            Query(
                id=stem.split("_", 1)[0],
                name=stem,
                title=_header(sql, "title"),
                question=_header(sql, "question"),
                technique=_header(sql, "technique"),
                sql=sql.strip().rstrip(";"),
            )
        )
    return queries


def fetch(conn: psycopg.Connection, sql: str) -> list[tuple[Any, ...]]:
    return conn.execute(sql).fetchall()


def result_digest(rows: list[tuple[Any, ...]]) -> str:
    """A hash of the result, stable across runs: values are written as text, one row per line."""
    text = "\n".join("\x1f".join("" if v is None else str(v) for v in row) for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _walk(plan: dict[str, Any], out: list[str]) -> None:
    label = str(plan["Node Type"])
    if "Index Name" in plan:
        label += f" using {plan['Index Name']}"
    out.append(label)
    for child in plan.get("Plans", []):
        _walk(child, out)


def explain(conn: psycopg.Connection, sql: str) -> Plan:
    row = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql).fetchone()
    assert row is not None
    doc = row[0][0]
    root = doc["Plan"]
    nodes: list[str] = []
    _walk(root, nodes)
    return Plan(
        execution_ms=float(doc["Execution Time"]),
        planning_ms=float(doc["Planning Time"]),
        root_node=str(root["Node Type"]),
        nodes=tuple(nodes),
        shared_hit=int(root.get("Shared Hit Blocks", 0)),
        shared_read=int(root.get("Shared Read Blocks", 0)),
    )


def measure(conn: psycopg.Connection, sql: str, repeat: int) -> Timing:
    """One warm-up execution, then `repeat` measured ones; the median is the number to quote."""
    explain(conn, sql)
    plans = [explain(conn, sql) for _ in range(max(1, repeat))]
    times = [p.execution_ms for p in plans]
    last = plans[-1]
    return Timing(
        median_ms=statistics.median(times),
        min_ms=min(times),
        max_ms=max(times),
        planning_ms=statistics.median(p.planning_ms for p in plans),
        root_node=last.root_node,
        nodes=last.nodes,
        shared_hit=last.shared_hit,
        shared_read=last.shared_read,
    )
