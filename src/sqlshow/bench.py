"""Index experiments: the same query measured with EXPLAIN (ANALYZE, BUFFERS) before and after an index.

Every experiment starts from the baseline schema (primary keys only), builds what it needs, measures, and drops
everything it built, even when it fails, so the experiments do not influence each other.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from sqlshow import queries
from sqlshow.queries import Timing


@dataclass(frozen=True)
class Experiment:
    id: str
    title: str
    why: str
    query: str  # may contain {placeholders} filled from the parameters
    candidate: tuple[str, ...]  # DDL that creates the index under test
    baseline: tuple[str, ...] = ()  # DDL that creates what the baseline already has
    indexes: tuple[str, ...] = ()  # names of the indexes the candidate creates (their size is reported)
    cleanup: tuple[str, ...] = ()  # DROP INDEX IF EXISTS ... for everything above
    baseline_label: str = "no index"
    candidate_label: str = ""


EXPERIMENTS: tuple[Experiment, ...] = (
    Experiment(
        id="e01",
        title="Index on a foreign key",
        why="PostgreSQL does not index a foreign key by itself. Without an index, finding one customer's orders reads the whole table.",
        query="SELECT order_id, ordered_at, status FROM orders WHERE customer_id = {customer_id}",
        candidate=("CREATE INDEX idx_orders_customer ON orders (customer_id)",),
        indexes=("idx_orders_customer",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_customer",),
        candidate_label="btree on customer_id",
    ),
    Experiment(
        id="e02",
        title="B-tree on a time range",
        why="A week of orders out of three years: a range condition on a column that has no index.",
        query=(
            "SELECT date_trunc('day', ordered_at) AS day, count(*) FROM orders "
            "WHERE ordered_at >= '2025-06-01' AND ordered_at < '2025-06-08' GROUP BY 1 ORDER BY 1"
        ),
        candidate=("CREATE INDEX idx_orders_time ON orders (ordered_at)",),
        indexes=("idx_orders_time",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_time",),
        candidate_label="btree on ordered_at",
    ),
    Experiment(
        id="e03",
        title="BRIN on a time range",
        why="The same query as e02. Order ids follow time, so the rows of a week are stored together, and a BRIN index "
        "(one entry per block range) can find them at a tiny fraction of the size of a B-tree.",
        query=(
            "SELECT date_trunc('day', ordered_at) AS day, count(*) FROM orders "
            "WHERE ordered_at >= '2025-06-01' AND ordered_at < '2025-06-08' GROUP BY 1 ORDER BY 1"
        ),
        candidate=("CREATE INDEX idx_orders_time_brin ON orders USING brin (ordered_at)",),
        indexes=("idx_orders_time_brin",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_time_brin",),
        candidate_label="BRIN on ordered_at",
    ),
    Experiment(
        id="e04",
        title="Composite index that also gives the order",
        why="The last five orders of a customer. An index on customer_id finds the rows but they still have to be sorted; "
        "an index on (customer_id, ordered_at DESC) returns them already in order and stops after five.",
        query="SELECT order_id, ordered_at FROM orders WHERE customer_id = {customer_id} ORDER BY ordered_at DESC LIMIT 5",
        baseline=("CREATE INDEX idx_orders_customer ON orders (customer_id)",),
        candidate=(
            "DROP INDEX idx_orders_customer",
            "CREATE INDEX idx_orders_customer_time ON orders (customer_id, ordered_at DESC)",
        ),
        indexes=("idx_orders_customer_time",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_customer", "DROP INDEX IF EXISTS idx_orders_customer_time"),
        baseline_label="btree on customer_id",
        candidate_label="btree on (customer_id, ordered_at DESC)",
    ),
    Experiment(
        id="e05",
        title="Covering index and an index-only scan",
        why="Counting the paid orders of a range of customers. If the index also holds the status column (INCLUDE), the "
        "table is not read at all, as long as the visibility map is up to date (hence the VACUUM).",
        query="SELECT count(*) FROM orders WHERE customer_id BETWEEN {customer_lo} AND {customer_hi} AND status = 'paid'",
        baseline=("CREATE INDEX idx_orders_customer ON orders (customer_id)",),
        candidate=(
            "DROP INDEX idx_orders_customer",
            "CREATE INDEX idx_orders_customer_status ON orders (customer_id) INCLUDE (status)",
        ),
        indexes=("idx_orders_customer_status",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_customer", "DROP INDEX IF EXISTS idx_orders_customer_status"),
        baseline_label="btree on customer_id",
        candidate_label="btree on customer_id INCLUDE (status)",
    ),
    Experiment(
        id="e06",
        title="Partial index",
        why="Pending orders are a tiny part of the table and are looked up constantly. An index that holds only those rows "
        "is small and cheap to keep.",
        query="SELECT order_id, customer_id FROM orders WHERE status = 'pending'",
        candidate=("CREATE INDEX idx_orders_pending ON orders (customer_id) WHERE status = 'pending'",),
        indexes=("idx_orders_pending",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_pending",),
        candidate_label="partial btree WHERE status = 'pending'",
    ),
    Experiment(
        id="e07",
        title="Expression index",
        why="Case-insensitive lookup by e-mail. A plain index on email cannot serve lower(email) = ...; an index on the "
        "expression can.",
        query="SELECT customer_id, country FROM customers WHERE lower(email) = {email}",
        candidate=("CREATE INDEX idx_customers_email ON customers (lower(email))",),
        indexes=("idx_customers_email",),
        cleanup=("DROP INDEX IF EXISTS idx_customers_email",),
        candidate_label="btree on lower(email)",
    ),
    Experiment(
        id="e08",
        title="GIN on a JSONB column",
        why="Events of one campaign, found by containment (@>) on a JSONB document.",
        query="SELECT count(*) FROM events WHERE props @> {campaign}::jsonb",
        candidate=("CREATE INDEX idx_events_props ON events USING gin (props jsonb_path_ops)",),
        indexes=("idx_events_props",),
        cleanup=("DROP INDEX IF EXISTS idx_events_props",),
        candidate_label="GIN (jsonb_path_ops) on props",
    ),
    Experiment(
        id="e09",
        title="Index on the foreign key of a large table",
        why="The revenue of one product, from the order lines (the biggest table of the shop).",
        query="SELECT sum(quantity * unit_price) AS revenue, count(*) AS lines FROM order_items WHERE product_id = {product_id}",
        candidate=("CREATE INDEX idx_items_product ON order_items (product_id)",),
        indexes=("idx_items_product",),
        cleanup=("DROP INDEX IF EXISTS idx_items_product",),
        candidate_label="btree on product_id",
    ),
    Experiment(
        id="e10",
        title="An index that barely helps",
        why="Customers with no orders, as a NOT EXISTS. The planner has to read the customer of every order either way, so an "
        "index on customer_id can only make that read cheaper, not skip it: the gain is small, unlike the other experiments.",
        query="SELECT count(*) FROM customers AS c WHERE NOT EXISTS (SELECT 1 FROM orders AS o WHERE o.customer_id = c.customer_id)",
        candidate=("CREATE INDEX idx_orders_customer ON orders (customer_id)",),
        indexes=("idx_orders_customer",),
        cleanup=("DROP INDEX IF EXISTS idx_orders_customer",),
        candidate_label="btree on customer_id",
    ),
)


def choose_parameters(conn: psycopg.Connection) -> dict[str, str]:
    """Literals for the queries, chosen from the data: a busy (not the busiest) customer and product, and so on."""

    def one(query: str) -> Any:
        row = conn.execute(query).fetchone()
        assert row is not None
        return row[0]

    n_customers = int(one("SELECT count(*) FROM customers"))
    customer = one(
        "SELECT customer_id FROM (SELECT customer_id, count(*) AS n FROM orders GROUP BY 1 ORDER BY n DESC, 1 LIMIT 50) t "
        "ORDER BY n, customer_id LIMIT 1"
    )
    product = one(
        "SELECT product_id FROM (SELECT product_id, count(*) AS n FROM order_items GROUP BY 1 ORDER BY n DESC, 1 LIMIT 20) t "
        "ORDER BY n, product_id LIMIT 1"
    )
    lo = n_customers // 4
    email = one("SELECT lower(email) FROM customers WHERE customer_id = %s" % (n_customers // 2))
    return {
        "customer_id": str(int(customer)),
        "product_id": str(int(product)),
        "customer_lo": str(lo),
        "customer_hi": str(lo + max(20, n_customers // 50)),
        "email": sql.Literal(email).as_string(conn),
        "campaign": sql.Literal('{"campaign": "c07"}').as_string(conn),
    }


def _run(conn: psycopg.Connection, statements: tuple[str, ...]) -> None:
    for statement in statements:
        conn.execute(statement)


def _index_bytes(conn: psycopg.Connection, names: tuple[str, ...]) -> int:
    total = 0
    for name in names:
        row = conn.execute("SELECT pg_relation_size(%s::regclass)", (name,)).fetchone()
        assert row is not None
        total += int(row[0])
    return total


def _timing(t: Timing) -> dict[str, Any]:
    return {
        "median_ms": round(t.median_ms, 3),
        "min_ms": round(t.min_ms, 3),
        "max_ms": round(t.max_ms, 3),
        "planning_ms": round(t.planning_ms, 3),
        "root_node": t.root_node,
        "nodes": list(t.nodes),
        "shared_hit": t.shared_hit,
        "shared_read": t.shared_read,
    }


def run_experiment(conn: psycopg.Connection, exp: Experiment, params: dict[str, str], repeat: int) -> dict[str, Any]:
    # the query text comes from the constants above and from literals made by psycopg, never from user input
    text = exp.query.format(**params)
    try:
        _run(conn, exp.cleanup)
        _run(conn, exp.baseline)
        conn.execute("VACUUM ANALYZE")
        before_rows = queries.fetch(conn, text)
        before = queries.measure(conn, text, repeat)

        started = time.perf_counter()
        _run(conn, exp.candidate)
        build_ms = (time.perf_counter() - started) * 1000
        conn.execute("VACUUM ANALYZE")
        after_rows = queries.fetch(conn, text)
        after = queries.measure(conn, text, repeat)
        if queries.result_digest(before_rows) != queries.result_digest(after_rows):
            raise RuntimeError(f"{exp.id}: the index changed the result of the query")
        size = _index_bytes(conn, exp.indexes)
    finally:
        _run(conn, exp.cleanup)
    return {
        "id": exp.id,
        "title": exp.title,
        "why": exp.why,
        "query": text,
        "rows": len(before_rows),
        "baseline_label": exp.baseline_label,
        "candidate_label": exp.candidate_label,
        "ddl": list(exp.candidate),
        "baseline": _timing(before),
        "candidate": _timing(after),
        "speedup": round(before.median_ms / after.median_ms, 2) if after.median_ms > 0 else None,
        "index_build_ms": round(build_ms, 1),
        "index_bytes": size,
    }


def run_all(
    conn: psycopg.Connection, repeat: int, progress: Callable[[str], None] | None = None
) -> list[dict[str, Any]]:
    params = choose_parameters(conn)
    results = []
    for exp in EXPERIMENTS:
        if progress:
            progress(f"experiment {exp.id}: {exp.title}")
        results.append(run_experiment(conn, exp, params, repeat))
    return results
