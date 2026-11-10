from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest

from sqlshow import cli, db, queries, report
from sqlshow.datagen import Dataset
from sqlshow.evaluate import evaluate


def fake_report() -> dict[str, Any]:
    timing = {
        "median_ms": 12.5,
        "min_ms": 11.0,
        "max_ms": 14.0,
        "planning_ms": 0.2,
        "root_node": "Seq Scan",
        "nodes": ["Seq Scan"],
        "shared_hit": 10,
        "shared_read": 2,
    }
    fast = {**timing, "median_ms": 0.25, "root_node": "Index Scan", "nodes": ["Index Scan using idx_a"]}
    return {
        "environment": {
            "sqlshow": "1.0.0",
            "python": "3.13.0",
            "psycopg": "3.3.0",
            "system": "Linux x86_64",
            "server": {"server_version": "18.6 (Debian)", "work_mem": "4MB"},
            "scale": 1.0,
            "seed": 1,
            "repeat": 5,
            "seconds": 3.0,
            "rows": {"orders": 1234},
            "table_bytes": {"orders": 5 * 1024 * 1024},
            "command": "evaluate",
        },
        "queries": [
            {
                "id": "q01",
                "title": "T",
                "question": "Q?",
                "technique": "tech",
                "rows": 3,
                **timing,
                "result_sha256": "0" * 64,
                "name": "q01_t",
            }
        ],
        "experiments": [
            {
                "id": "e01",
                "title": "E",
                "why": "because",
                "query": "SELECT 1",
                "rows": 1,
                "baseline_label": "none",
                "candidate_label": "btree",
                "ddl": ["CREATE INDEX i ON t (c)"],
                "baseline": timing,
                "candidate": fast,
                "speedup": 50.0,
                "index_build_ms": 4.0,
                "index_bytes": 2048,
            }
        ],
    }


def test_formatting() -> None:
    assert report.ms(0.256) == "0.26" and report.ms(1234.56) == "1,234.6"
    assert report.size(512) == "512 B" and report.size(2048) == "2.0 KiB" and report.size(5 * 1024**2) == "5.0 MiB"
    assert report.size(3 * 1024**3) == "3.0 GiB"
    assert report.speed(None) == "n/a" and report.speed(12.34) == "12.3x"
    nodes = ["Limit", "Subquery Scan", "Index Only Scan using i", "Seq Scan", "Seq Scan", "CTE Scan"]
    assert report.scan_kinds(nodes) == "Index Only Scan using i, Seq Scan"
    assert report.scan_kinds(["Aggregate"]) == "none"


def test_markdown_and_figure_come_from_the_json(tmp_path: Path) -> None:
    md = report.render_markdown(fake_report())
    for text in (
        "PostgreSQL 18.6 (Debian)",
        "| orders | 1,234 | 5.0 MiB |",
        "| q01 T | 3 | 12.5 |",
        "| e01 E | 12.5 | 0.25 | 50.0x |",
        "```sql\nSELECT 1\n```",
        "Index Scan using idx_a",
    ):
        assert text in md, text
    png = tmp_path / "s.png"
    report.summary_figure(fake_report(), png)
    assert png.stat().st_size > 10_000


def test_cli_errors_exit_with_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.delenv(db.DSN_ENV, raising=False)
    assert cli.main(["run"]) == 2 and "no database given" in capsys.readouterr().err
    assert cli.main(["init", "--dsn", "postgresql://nobody@127.0.0.1:1/none"]) == 2
    assert "cannot connect" in capsys.readouterr().err
    assert cli.main(["render", str(tmp_path / "missing.json"), "-o", str(tmp_path / "x.md")]) == 2
    assert cli.main(["init", "--scale", "0"]) == 2


def test_queries_command_lists_everything(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["queries"]) == 0
    out = capsys.readouterr().out
    for q in queries.load_queries():
        assert q.id in out and q.title in out


def test_render_rebuilds_identically(tmp_path: Path) -> None:
    src = tmp_path / "report.json"
    src.write_text(json.dumps(fake_report()), encoding="utf-8")
    assert cli.main(["render", str(src), "-o", str(tmp_path / "a.md"), "--figure", str(tmp_path / "a.png")]) == 0
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == report.render_markdown(fake_report())
    assert (tmp_path / "a.png").exists()


def test_run_bench_and_evaluate_end_to_end(
    dsn: str, conn: psycopg.Connection, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "--dsn", dsn, "--only", "q01,q02", "--repeat", "1"]) == 0
    out = capsys.readouterr().out
    assert "q01" in out and "q02" in out and "q03" not in out
    assert cli.main(["run", "--dsn", dsn, "--only", "q99"]) == 2
    assert "unknown id: q99" in capsys.readouterr().err
    assert cli.main(["bench", "--dsn", dsn, "--only", "e01,e07", "--repeat", "1"]) == 0
    assert "e07" in capsys.readouterr().out
    assert cli.main(["evaluate", "--dsn", dsn, "--repeat", "1", "--out", str(tmp_path / "out")]) == 0
    result = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert [q["id"] for q in result["queries"]] == [q.id for q in queries.load_queries()]
    assert len(result["experiments"]) == 10 and result["environment"]["scale"] == 0.02
    assert (tmp_path / "out" / "summary.png").exists()
    md = (tmp_path / "out" / "evaluation.md").read_text(encoding="utf-8")
    assert md == report.render_markdown(result)
    # a second evaluation of the same data gives the same results (the timings differ, the answers do not)
    again = evaluate(conn, 1, "again")
    assert [q["result_sha256"] for q in again["queries"]] == [q["result_sha256"] for q in result["queries"]]
    assert [q["rows"] for q in again["queries"]] == [q["rows"] for q in result["queries"]]


def test_init_replaces_the_schema_and_leaves_the_rest_alone(
    dsn: str, conn: psycopg.Connection, restore: None, data: Dataset, capsys: pytest.CaptureFixture[str]
) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS public.sqlshow_sentinel (x int)")
    try:
        assert cli.main(["init", "--dsn", dsn, "--scale", "0.01", "--seed", "3"]) == 0
        assert "scale 0.01, seed 3" in capsys.readouterr().out
        meta = db.meta(conn)
        assert meta["scale"] == "0.01" and meta["seed"] == "3" and meta["rows_orders"] == "2000"
        assert conn.execute("SELECT count(*) FROM public.sqlshow_sentinel").fetchone() == (0,)
    finally:
        conn.execute("DROP TABLE IF EXISTS public.sqlshow_sentinel")


def test_meta_without_data_says_what_to_do(dsn: str, restore: None) -> None:
    with db.connect(dsn) as c:
        c.execute("DROP SCHEMA IF EXISTS sqlshow CASCADE")
        c.execute("CREATE SCHEMA sqlshow")
        with pytest.raises(db.ConfigError, match="sqlshow init"):
            db.meta(c)


def test_server_info_has_the_settings_that_matter(conn: psycopg.Connection) -> None:
    info = db.server_info(conn)
    assert info["jit"] == "off" and "work_mem" in info and info["server_version"][0].isdigit()
    sizes = db.table_sizes(conn)
    assert sizes["orders"] > 0 and "meta" in sizes
