from __future__ import annotations

import psycopg
import pytest

from sqlshow import bench, db, queries
from sqlshow.evaluate import check_baseline


def test_experiments_are_well_formed() -> None:
    assert [e.id for e in bench.EXPERIMENTS] == [f"e{i:02d}" for i in range(1, 11)]
    for e in bench.EXPERIMENTS:
        assert e.title and e.why and e.candidate and e.cleanup and e.indexes
        for name in e.indexes:
            assert f"DROP INDEX IF EXISTS {name}" in e.cleanup, (e.id, name)


def test_parameters_are_literals_from_the_data(conn: psycopg.Connection) -> None:
    p = bench.choose_parameters(conn)
    assert int(p["customer_id"]) > 0 and int(p["product_id"]) > 0
    assert int(p["customer_hi"]) > int(p["customer_lo"])
    assert p["email"].startswith("'user") and p["email"].endswith("@example.com'")
    assert p["campaign"] == """'{"campaign": "c07"}'"""


def test_every_experiment_runs_and_leaves_no_index_behind(conn: psycopg.Connection) -> None:
    results = bench.run_all(conn, repeat=2)
    assert [r["id"] for r in results] == [e.id for e in bench.EXPERIMENTS]
    for r in results:
        assert r["baseline"]["median_ms"] > 0 and r["candidate"]["median_ms"] > 0
        assert r["speedup"] is not None and r["index_bytes"] > 0 and r["index_build_ms"] > 0
        assert r["baseline"]["nodes"] and r["candidate"]["nodes"]
        assert r["baseline"]["min_ms"] <= r["baseline"]["median_ms"] <= r["baseline"]["max_ms"]
    check_baseline(conn)  # only primary keys remain


def test_the_index_is_what_the_plan_uses_when_it_clearly_should(conn: psycopg.Connection) -> None:
    exp = next(e for e in bench.EXPERIMENTS if e.id == "e07")  # one row out of hundreds, by an expression
    r = bench.run_experiment(conn, exp, bench.choose_parameters(conn), repeat=1)
    assert "Seq Scan" in r["baseline"]["nodes"][0] or r["baseline"]["root_node"] == "Seq Scan"
    assert any("idx_customers_email" in n for n in r["candidate"]["nodes"])
    assert r["rows"] == 1


def test_a_failing_experiment_still_cleans_up(conn: psycopg.Connection) -> None:
    broken = bench.Experiment(
        id="x",
        title="t",
        why="w",
        query="SELECT * FROM no_such_table",
        candidate=("CREATE INDEX idx_x ON orders (customer_id)",),
        baseline=("CREATE INDEX idx_x2 ON orders (customer_id)",),
        indexes=("idx_x",),
        cleanup=("DROP INDEX IF EXISTS idx_x", "DROP INDEX IF EXISTS idx_x2"),
    )
    with pytest.raises(psycopg.Error):
        bench.run_experiment(conn, broken, {}, repeat=1)
    check_baseline(conn)


def test_an_index_that_changed_the_result_is_refused(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    digests = iter(["a", "b"])
    monkeypatch.setattr(queries, "result_digest", lambda rows: next(digests))
    exp = bench.EXPERIMENTS[0]
    with pytest.raises(RuntimeError, match="changed the result"):
        bench.run_experiment(conn, exp, bench.choose_parameters(conn), repeat=1)
    check_baseline(conn)


def test_check_baseline_names_extra_indexes(conn: psycopg.Connection) -> None:
    conn.execute("CREATE INDEX idx_stray ON orders (status)")
    try:
        with pytest.raises(db.ConfigError, match="idx_stray"):
            check_baseline(conn)
    finally:
        conn.execute("DROP INDEX idx_stray")
    check_baseline(conn)
