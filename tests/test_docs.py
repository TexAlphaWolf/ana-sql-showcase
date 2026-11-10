"""The README and the docs quote the measured numbers: they are checked here against docs/report.json."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from sqlshow.report import ms, size, speed

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
REPORT: dict[str, Any] = json.loads((ROOT / "docs" / "report.json").read_text(encoding="utf-8"))
REPORT_MD = (ROOT / "docs" / "evaluation.md").read_text(encoding="utf-8")
DOCS = ["analysis", "architecture", "limitations", "method"]


def test_report_is_the_full_run() -> None:
    env = REPORT["environment"]
    assert env["scale"] == 1.0
    assert env["server"]["server_version"].startswith("18")
    assert env["rows"]["orders"] == 200_000
    assert len(REPORT["queries"]) == 13
    assert len(REPORT["experiments"]) == 10
    assert all(q["rows"] > 0 for q in REPORT["queries"])


@pytest.mark.parametrize("q", REPORT["queries"], ids=lambda q: q["id"])
def test_readme_query_row(q: dict[str, Any]) -> None:
    pattern = rf"\| {q['id']} {re.escape(q['title'])} \| .* \| {re.escape(ms(q['median_ms']))} \|"
    assert re.search(pattern, README), q["id"]


@pytest.mark.parametrize("e", REPORT["experiments"], ids=lambda e: e["id"])
def test_readme_experiment_row(e: dict[str, Any]) -> None:
    row = (
        rf"\| {e['id']} {re.escape(e['title'])} \| {re.escape(ms(e['baseline']['median_ms']))} \| "
        rf"{re.escape(ms(e['candidate']['median_ms']))} \| {re.escape(speed(e['speedup']))} \| "
        rf"{re.escape(size(e['index_bytes']))} \|"
    )
    assert re.search(row, README), e["id"]


def test_readme_headline_numbers() -> None:
    q = {x["id"]: x["median_ms"] for x in REPORT["queries"]}
    e = {x["id"]: x for x in REPORT["experiments"]}
    assert f"{round(min(q.values()))} to {round(max(q.values()))} ms" in README
    assert f"{speed(e['e07']['speedup'])}" in README and f"{speed(e['e06']['speedup'])}" in README
    assert f"{speed(e['e01']['speedup'])}" in README
    assert f"{e['e03']['index_bytes'] / 1024:.1f} KiB" in README
    ratio = round(e["e02"]["index_bytes"] / e["e03"]["index_bytes"])
    assert f"{ratio} times larger" in README
    assert f"PostgreSQL {REPORT['environment']['server']['server_version'].split()[0]}" in README
    assert f"{REPORT['environment']['rows']['events']:,} events" in README
    assert f"{REPORT['environment']['seconds']:.0f} s" in README


def test_analysis_numbers() -> None:
    text = (ROOT / "docs" / "analysis.md").read_text(encoding="utf-8")
    for e in REPORT["experiments"]:
        assert speed(e["speedup"]) in text, e["id"]
    q11 = next(q for q in REPORT["queries"] if q["id"] == "q11")
    assert f"{q11['shared_hit']:,} buffers" in text


def test_every_query_is_a_seq_scan_without_disk_reads() -> None:
    for q in REPORT["queries"]:
        assert "Seq Scan" in q["nodes"], q["id"]
        assert q["shared_read"] == 0, q["id"]


def test_evaluation_md_is_what_render_gives() -> None:
    from sqlshow.report import render_markdown

    assert render_markdown(REPORT) == REPORT_MD


def test_no_scaffold_left() -> None:
    for name in ["README.md", *(f"docs/{d}.md" for d in DOCS)]:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "Work in progress" not in text and "TODO" not in text, name


def test_local_links_resolve() -> None:
    files = [ROOT / "README.md", *(ROOT / "docs" / f"{d}.md" for d in DOCS)]
    for f in files:
        for target in re.findall(r"\]\(([^)#]+)\)", f.read_text(encoding="utf-8")):
            if target.startswith(("http", "mailto")):
                continue
            assert (f.parent / target).exists(), f"{f.name}: {target}"


def test_figure_exists() -> None:
    assert (ROOT / "docs" / "summary.png").stat().st_size > 10_000
