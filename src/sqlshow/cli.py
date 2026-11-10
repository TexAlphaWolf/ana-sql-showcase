"""Command line: init, queries, run, bench, evaluate, render."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import psycopg

from sqlshow import __version__, bench, db, queries
from sqlshow.evaluate import check_baseline, evaluate
from sqlshow.report import ms, render_markdown, speed, summary_figure


def _add_connection(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dsn", help=f"PostgreSQL connection string (default: ${db.DSN_ENV})")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sqlshow", description=__doc__)
    ap.add_argument("--version", action="version", version=f"sqlshow {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help=f"(re)create the schema '{db.SCHEMA}' and load synthetic data")
    _add_connection(p)
    p.add_argument("--scale", type=float, default=1.0, help="1.0 = 20,000 customers, 200,000 orders, ~500,000 events")
    p.add_argument("--seed", type=int, default=1)

    sub.add_parser("queries", help="list the queries with their question and technique")

    p = sub.add_parser("run", help="run the queries and print rows and median time")
    _add_connection(p)
    p.add_argument("--only", help="comma separated ids, for example q01,q07")
    p.add_argument("--repeat", type=int, default=5)

    p = sub.add_parser("bench", help="run the index experiments")
    _add_connection(p)
    p.add_argument("--only", help="comma separated ids, for example e01,e04")
    p.add_argument("--repeat", type=int, default=5)

    p = sub.add_parser("evaluate", help="queries and experiments, written as report.json, evaluation.md, summary.png")
    _add_connection(p)
    p.add_argument("--out", default="sqlshow-out")
    p.add_argument("--repeat", type=int, default=5)

    p = sub.add_parser("render", help="rebuild the Markdown (and the figure) from a report.json")
    p.add_argument("report")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--figure")
    return ap


def _pick(only: str | None, known: list[str]) -> list[str]:
    if not only:
        return known
    wanted = [x.strip() for x in only.split(",") if x.strip()]
    unknown = [x for x in wanted if x not in known]
    if unknown:
        raise db.ConfigError(f"unknown id: {', '.join(unknown)} (known: {', '.join(known)})")
    return wanted


def _cmd_init(args: argparse.Namespace) -> int:
    if args.scale <= 0:
        raise db.ConfigError("--scale must be positive")
    with db.connect(args.dsn) as conn:
        data = db.init(conn, args.scale, args.seed)
    counts = ", ".join(f"{n:,} {name}" for name, n in data.counts().items())
    print(f"loaded into schema '{db.SCHEMA}' (scale {args.scale:g}, seed {args.seed}): {counts}")
    return 0


def _cmd_queries(_: argparse.Namespace) -> int:
    for q in queries.load_queries():
        print(f"{q.id}  {q.title}\n     {q.question}\n     technique: {q.technique}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    with db.connect(args.dsn) as conn:
        db.meta(conn)
        check_baseline(conn)
        wanted = _pick(args.only, [q.id for q in queries.load_queries()])
        for q in queries.load_queries():
            if q.id not in wanted:
                continue
            rows = queries.fetch(conn, q.sql)
            t = queries.measure(conn, q.sql, args.repeat)
            print(f"{q.id}  {q.title:<46} {len(rows):>6,} rows  {ms(t.median_ms):>9} ms  {t.root_node}")
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    with db.connect(args.dsn) as conn:
        db.meta(conn)
        check_baseline(conn)
        wanted = _pick(args.only, [e.id for e in bench.EXPERIMENTS])
        params = bench.choose_parameters(conn)
        for exp in bench.EXPERIMENTS:
            if exp.id not in wanted:
                continue
            r = bench.run_experiment(conn, exp, params, args.repeat)
            print(
                f"{r['id']}  {r['title']:<44} {ms(r['baseline']['median_ms']):>9} ms -> "
                f"{ms(r['candidate']['median_ms']):>9} ms  {speed(r['speedup']):>7}"
            )
    return 0


def _write_outputs(report: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "evaluation.md").write_text(render_markdown(report), encoding="utf-8")
    summary_figure(report, out / "summary.png")
    print(f"written: {out / 'report.json'}, {out / 'evaluation.md'}, {out / 'summary.png'}")


def _cmd_evaluate(args: argparse.Namespace) -> int:
    with db.connect(args.dsn) as conn:
        report = evaluate(
            conn,
            args.repeat,
            "evaluate " + " ".join(sys.argv[2:]),
            progress=lambda m: print(m, file=sys.stderr, flush=True),
        )
    _write_outputs(report, Path(args.out))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise db.ConfigError(f"cannot read {args.report}: {exc}") from exc
    Path(args.output).write_text(render_markdown(report), encoding="utf-8")
    if args.figure:
        summary_figure(report, Path(args.figure))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {
        "init": _cmd_init,
        "queries": _cmd_queries,
        "run": _cmd_run,
        "bench": _cmd_bench,
        "evaluate": _cmd_evaluate,
        "render": _cmd_render,
    }
    try:
        return handlers[args.cmd](args)
    except db.ConfigError as exc:
        print(f"sqlshow: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        print(f"sqlshow: database error: {str(exc).strip()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
