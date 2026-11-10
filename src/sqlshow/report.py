"""The Markdown report and the summary figure, both built from report.json alone (so `sqlshow render` rebuilds them)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BEFORE = "#8a8f98"
AFTER = "#0072B2"
DATA_NODES = ("Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Bitmap Index Scan")


def ms(value: float) -> str:
    return f"{value:.2f}" if value < 10 else f"{value:,.1f}"


def size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KiB", 1024), ("MiB", 1024**2), ("GiB", 1024**3)):
        if n < div * 1024 or unit == "GiB":
            return f"{n / div:.1f} {unit}"
    raise AssertionError("unreachable")


def speed(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}x"


def scan_kinds(nodes: list[str]) -> str:
    """The ways the data was read, from a plan's node list: 'Seq Scan' and 'Index Scan using idx_x' and so on."""
    kinds = [n for n in nodes if n.startswith(DATA_NODES)]
    return ", ".join(dict.fromkeys(kinds)) or "none"


def render_markdown(report: dict[str, Any]) -> str:
    env, srv = report["environment"], report["environment"]["server"]
    out = ["# Evaluation", ""]
    out.append(
        f"Run on {env['system']}, Python {env['python']}, psycopg {env['psycopg']}, PostgreSQL {srv['server_version']}; "
        f"scale {env['scale']:g}, seed {env['seed']}; {env['seconds']:.0f} s; each timing is the median of "
        f"{env['repeat']} executions after one warm-up (EXPLAIN ANALYZE, JIT off); command `{env['command']}`."
    )
    out.append("")
    out.append("## 1. The data")
    out.append("")
    out.append("| Table | Rows | Size with indexes |")
    out.append("|---|---|---|")
    for table, n in env["rows"].items():
        out.append(f"| {table} | {n:,} | {size(env['table_bytes'][table])} |")
    out.append("")
    settings = ", ".join(f"{k} = {v}" for k, v in srv.items() if k != "server_version")
    out.append(f"Server settings: {settings}.")
    out.append("")
    out.append("## 2. The queries")
    out.append("")
    out.append(
        "Run on the baseline schema (primary keys only). Each result is checked against an independent computation in "
        "Python by the tests; here the row count and a hash of the result are recorded."
    )
    out.append("")
    out.append("| Query | Rows | Median (ms) | Planning (ms) | Buffers hit / read | Data read by |")
    out.append("|---|---|---|---|---|---|")
    for q in report["queries"]:
        out.append(
            f"| {q['id']} {q['title']} | {q['rows']:,} | {ms(q['median_ms'])} | {ms(q['planning_ms'])} "
            f"| {q['shared_hit']:,} / {q['shared_read']:,} | {scan_kinds(q['nodes'])} |"
        )
    out.append("")
    for q in report["queries"]:
        out.append(f"- **{q['id']}**: {q['question']} *{q['technique']}.* Plan: {' > '.join(q['nodes'][:6])}.")
    out.append("")
    out.append("## 3. Index experiments")
    out.append("")
    out.append(
        "Each experiment measures one query before and after an index, with everything else equal, and drops what it built."
    )
    out.append("")
    out.append(
        "| Experiment | Before (ms) | After (ms) | Speed-up | Data read before | Data read after | Index size | Build (ms) |"
    )
    out.append("|---|---|---|---|---|---|---|---|")
    for e in report["experiments"]:
        b, a = e["baseline"], e["candidate"]
        out.append(
            f"| {e['id']} {e['title']} | {ms(b['median_ms'])} | {ms(a['median_ms'])} | {speed(e['speedup'])} "
            f"| {scan_kinds(b['nodes'])} | {scan_kinds(a['nodes'])} | {size(e['index_bytes'])} | {ms(e['index_build_ms'])} |"
        )
    out.append("")
    for e in report["experiments"]:
        out.append(f"### {e['id']} {e['title']}")
        out.append("")
        out.append(e["why"])
        out.append("")
        out.append(f"```sql\n{e['query']}\n```")
        out.append("")
        out.append(f"Before: {e['baseline_label']}. After: {e['candidate_label']} (`{'; '.join(e['ddl'])}`).")
        out.append("")
        out.append(
            f"Rows returned: {e['rows']:,}. Buffers hit / read: {e['baseline']['shared_hit']:,} / "
            f"{e['baseline']['shared_read']:,} before, {e['candidate']['shared_hit']:,} / {e['candidate']['shared_read']:,} after."
        )
        out.append("")
    return "\n".join(out) + "\n"


def summary_figure(report: dict[str, Any], path: Path) -> None:
    queries, experiments = report["queries"], report["experiments"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={"width_ratios": [1, 1.25]})

    labels = [f"{q['id']}  {q['title']}" for q in queries]
    left.barh(labels, [q["median_ms"] for q in queries], color=AFTER)
    left.invert_yaxis()
    left.set_xlabel("median execution time (ms)")
    left.set_title("The 13 queries on the baseline schema")
    left.tick_params(axis="y", labelsize=8)
    for i, q in enumerate(queries):
        left.text(
            q["median_ms"] + max(x["median_ms"] for x in queries) * 0.01, i, ms(q["median_ms"]), va="center", fontsize=7
        )
    left.grid(axis="x", alpha=0.3)

    names = [f"{e['id']}  {e['title']}" for e in experiments]
    pos = list(range(len(experiments)))
    h = 0.38
    right.barh(
        [p - h / 2 for p in pos], [e["baseline"]["median_ms"] for e in experiments], h, color=BEFORE, label="before"
    )
    right.barh(
        [p + h / 2 for p in pos],
        [e["candidate"]["median_ms"] for e in experiments],
        h,
        color=AFTER,
        label="after the index",
    )
    right.set_yticks(pos, names)
    right.invert_yaxis()
    right.set_xscale("log")
    right.set_xlabel("median execution time (ms, log scale)")
    right.set_title("The same query before and after an index")
    right.tick_params(axis="y", labelsize=8)
    for p, e in zip(pos, experiments, strict=True):
        right.text(
            max(e["baseline"]["median_ms"], e["candidate"]["median_ms"]) * 1.15,
            p,
            speed(e["speedup"]),
            va="center",
            fontsize=8,
        )
    right.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=2, fontsize=8, frameon=False)
    right.grid(axis="x", alpha=0.3)

    version = report["environment"]["server"]["server_version"].split()[0]
    fig.suptitle(f"sqlshow on PostgreSQL {version}", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
