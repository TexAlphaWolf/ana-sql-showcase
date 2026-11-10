"""Every query is compared with the same answer computed in Python from the generated rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg
import pytest

from sqlshow import queries
from sqlshow.datagen import Dataset

from .reference import Reference

ALL = queries.load_queries()


def canonical(rows: list[tuple[Any, ...]]) -> list[str]:
    """Order-free comparison (text ordering depends on the database collation): rows as sorted strings."""
    return sorted(repr(tuple(format(v.normalize(), "f") if isinstance(v, Decimal) else v for v in r)) for r in rows)


def test_there_are_thirteen_queries_with_headers() -> None:
    assert [q.id for q in ALL] == [f"q{i:02d}" for i in range(1, 14)]
    for q in ALL:
        assert q.title and q.question
        assert q.technique and "--" not in q.sql.splitlines()[-1] and not q.sql.endswith(";")


def test_database_has_the_generated_data(conn: psycopg.Connection, data: Dataset) -> None:
    for table, n in data.counts().items():
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None and row[0] == n, table


@pytest.mark.parametrize("query", ALL, ids=lambda q: q.id)
def test_query_matches_the_reference(query: queries.Query, conn: psycopg.Connection, data: Dataset) -> None:
    got = queries.fetch(conn, query.sql)
    want = getattr(Reference(data), query.id)()
    assert got, "the query returns nothing: the data does not exercise it"
    if query.id == "q09":  # percentiles are floating point
        assert len(got) == len(want)
        for g, w in zip(sorted(got), sorted(want), strict=True):
            assert g[:2] == w[:2] and g[5] == w[5]
            assert all(abs(float(a) - b) < 0.0101 for a, b in zip(g[2:5], w[2:5], strict=True))
        return
    assert len(got) == len(want)
    assert canonical(got) == canonical(want)


def test_ordered_queries_come_back_in_their_order(conn: psycopg.Connection) -> None:
    by_id = {q.id: q for q in ALL}
    q02 = queries.fetch(conn, by_id["q02"].sql)
    assert [r[0] for r in q02] == sorted(r[0] for r in q02)
    q04 = queries.fetch(conn, by_id["q04"].sql)
    assert [r[1] for r in q04] == sorted((r[1] for r in q04), reverse=True)
    q05 = queries.fetch(conn, by_id["q05"].sql)
    assert [r[1] for r in q05] == sorted((r[1] for r in q05), reverse=True)
    assert [r[3] for r in q05] == sorted(r[3] for r in q05)  # A, then B, then C


def test_the_data_exercises_the_edge_cases(conn: psycopg.Connection, data: Dataset) -> None:
    ref = Reference(data)
    # a session boundary of exactly 30 minutes exists and does not split a session
    per: dict[int, list[int]] = {}
    for _, cust, ts, _, _ in data.events:
        per.setdefault(cust, []).append(ts)
    gaps = [b - a for ts in per.values() for a, b in zip(sorted(ts), sorted(ts)[1:], strict=False)]
    assert 1800 in gaps and any(g > 1800 for g in gaps)
    assert len(ref.q08()) == 10 and ref.q08()[0][1] >= 3  # a real streak
    assert {r[0] for r in ref.q04()} >= {"champions", "at risk"}
    statuses = {o[3] for o in data.orders}
    assert statuses == {"paid", "shipped", "refunded", "cancelled", "pending"}


def test_digest_is_stable(conn: psycopg.Connection) -> None:
    q = ALL[0]
    assert queries.result_digest(queries.fetch(conn, q.sql)) == queries.result_digest(queries.fetch(conn, q.sql))
    assert len(queries.result_digest([])) == 64
