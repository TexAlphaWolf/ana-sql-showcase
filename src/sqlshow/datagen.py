"""Synthetic data for a small online shop, made from a seed so that every run (and every test) sees the same rows.

Money is kept as integer cents and times as integer seconds since the epoch (UTC) until the rows are written to the
database; the tests compute the expected answers from these same values, independently of SQL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
from numpy.typing import NDArray

START_EPOCH = int(datetime(2023, 1, 1, tzinfo=UTC).timestamp())
END_EPOCH = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
START_DATE = date(2023, 1, 1)
TOP_CATEGORIES = ("Electronics", "Home", "Fashion", "Sports", "Books")
COUNTRIES = ("IT", "DE", "FR", "ES", "GB", "US", "NL", "PL")
COUNTRY_WEIGHTS = (0.30, 0.18, 0.14, 0.10, 0.09, 0.08, 0.06, 0.05)
STATUSES = ("paid", "shipped", "refunded", "cancelled")
STATUS_WEIGHTS = (0.72, 0.21, 0.04, 0.03)
PENDING_DAYS = 14
EVENT_KINDS = ("view", "search", "add_to_cart", "checkout")
EVENT_WEIGHTS = (0.60, 0.15, 0.15, 0.10)
DEVICES = ("mobile", "desktop", "tablet")
CAMPAIGNS = 50


@dataclass(frozen=True)
class Sizes:
    customers: int
    products: int
    orders: int
    events: int


def sizes(scale: float) -> Sizes:
    """Row counts for a scale: 1.0 is 20,000 customers, 200,000 orders and 500,000 events."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    return Sizes(
        customers=max(200, round(20_000 * scale)),
        products=max(120, round(2_000 * scale)),
        orders=max(2_000, round(200_000 * scale)),
        events=max(5_000, round(500_000 * scale)),
    )


@dataclass
class Dataset:
    """Rows of every table, as plain tuples in column order (see sql/schema.sql)."""

    scale: float
    seed: int
    categories: list[tuple[int, int | None, str]]
    products: list[tuple[int, int, str, int]]  # price in cents
    customers: list[tuple[int, str, str, date]]
    orders: list[tuple[int, int, int, str]]  # ordered_at as epoch seconds
    order_items: list[tuple[int, int, int, int, int]]  # unit price in cents
    events: list[tuple[int, int, int, str, dict[str, str]]]  # occurred_at as epoch seconds

    def counts(self) -> dict[str, int]:
        return {
            "categories": len(self.categories),
            "products": len(self.products),
            "customers": len(self.customers),
            "orders": len(self.orders),
            "order_items": len(self.order_items),
            "events": len(self.events),
        }


def cents(value: int) -> str:
    """12345 -> '123.45' (what COPY writes into a numeric column)."""
    return f"{value // 100}.{value % 100:02d}"


def timestamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(sep=" ")


def props_json(props: dict[str, str]) -> str:
    return json.dumps(props, sort_keys=True)


def _categories() -> tuple[list[tuple[int, int | None, str]], list[int]]:
    rows: list[tuple[int, int | None, str]] = []
    names: dict[int, str] = {}
    for i, top in enumerate(TOP_CATEGORIES, start=1):
        rows.append((i, None, top))
        names[i] = top
    next_id = len(TOP_CATEGORIES) + 1
    second: list[int] = []
    for parent in range(1, len(TOP_CATEGORIES) + 1):
        for j in range(4):
            names[next_id] = f"{names[parent]} {chr(65 + j)}"
            rows.append((next_id, parent, names[next_id]))
            second.append(next_id)
            next_id += 1
    leaves: list[int] = []
    for parent in second:
        for k in range(3):
            rows.append((next_id, parent, f"{names[parent]}{k + 1}"))
            leaves.append(next_id)
            next_id += 1
    return rows, leaves


def _weights(rng: np.random.Generator, n: int, shape: float) -> NDArray[np.float64]:
    w = rng.pareto(shape, n) + 1.0
    return np.asarray(w / w.sum(), dtype=np.float64)


def generate(scale: float = 1.0, seed: int = 1) -> Dataset:
    """Make the whole dataset. The same (scale, seed) always gives the same rows."""
    n = sizes(scale)
    rng = np.random.default_rng(seed)
    span = END_EPOCH - START_EPOCH

    categories, leaves = _categories()

    price_cents = np.clip(np.round(rng.lognormal(7.8, 0.9, n.products)), 199, 99_999).astype(int)
    product_cat = rng.choice(leaves, n.products)
    products = [(i + 1, int(product_cat[i]), f"Product {i + 1}", int(price_cents[i])) for i in range(n.products)]

    country = rng.choice(len(COUNTRIES), n.customers, p=COUNTRY_WEIGHTS)
    signup = rng.integers(0, 1096, n.customers)
    mixed_case = rng.random(n.customers) < 0.3
    customers = []
    for i in range(n.customers):
        email = f"User{i + 1}@Example.com" if mixed_case[i] else f"user{i + 1}@example.com"
        customers.append((i + 1, email, COUNTRIES[country[i]], START_DATE + timedelta(days=int(signup[i]))))

    # orders: later months have more orders; ids follow time, as they would in a real system
    order_customer = rng.choice(n.customers, n.orders, p=_weights(rng, n.customers, 1.5)) + 1
    order_time = np.sort(START_EPOCH + (span * rng.random(n.orders) ** 0.625).astype(np.int64))
    status_idx = rng.choice(len(STATUSES), n.orders, p=STATUS_WEIGHTS)
    pending = (order_time >= END_EPOCH - PENDING_DAYS * 86400) & (rng.random(n.orders) < 0.2)
    orders = [
        (i + 1, int(order_customer[i]), int(order_time[i]), "pending" if pending[i] else STATUSES[status_idx[i]])
        for i in range(n.orders)
    ]

    lines = np.minimum(rng.geometric(0.45, n.orders), 8)
    product_pick = rng.choice(n.products, int(lines.sum()), p=_weights(rng, n.products, 1.2)) + 1
    quantity = np.minimum(rng.geometric(0.7, len(product_pick)), 5)
    discounted = rng.random(len(product_pick)) < 0.2
    items: list[tuple[int, int, int, int, int]] = []
    pos = 0
    for order_id, k in enumerate(lines, start=1):
        seen: dict[int, None] = {}
        for p in product_pick[pos : pos + int(k)]:
            seen.setdefault(int(p), None)
        for line_no, p in enumerate(seen, start=1):
            price = products[p - 1][3]
            unit = max(1, round(price * 0.9)) if discounted[pos + line_no - 1] else price
            items.append((order_id, line_no, p, int(quantity[pos + line_no - 1]), unit))
        pos += int(k)

    events = _events(rng, n, span)
    return Dataset(scale, seed, categories, products, customers, orders, items, events)


def _events(rng: np.random.Generator, n: Sizes, span: int) -> list[tuple[int, int, int, str, dict[str, str]]]:
    """Visits of customers (a few customers visit a lot), each with 1 to 10 events a few minutes apart.

    Some gaps inside a visit are 30 minutes or more, including exactly 30 minutes, so that the session rule is tested
    at its boundary.
    """
    visits = max(1, n.events // 5)
    visit_customer = rng.choice(n.customers, visits, p=_weights(rng, n.customers, 1.1)) + 1
    visit_start = START_EPOCH + rng.integers(0, span, visits)
    per_visit = rng.integers(1, 11, visits)
    total = int(per_visit.sum())
    gap = np.ceil(rng.exponential(120, total)).astype(np.int64) + 1
    long_gap = rng.random(total) < 0.05
    gap[long_gap] = rng.choice([1800, 1801, 2400, 3600], int(long_gap.sum()))
    first = np.cumsum(per_visit) - per_visit
    gap[first] = 0
    running = np.cumsum(gap)
    offset = running - np.repeat(running[first], per_visit)
    when = np.repeat(visit_start, per_visit) + offset
    customer = np.repeat(visit_customer, per_visit)
    keep = when < END_EPOCH
    when, customer = when[keep], customer[keep]
    order = np.argsort(when, kind="stable")
    when, customer = when[order], customer[order]
    kind = rng.choice(len(EVENT_KINDS), len(when), p=EVENT_WEIGHTS)
    device = rng.choice(len(DEVICES), len(when))
    campaign = rng.integers(0, CAMPAIGNS * 4, len(when))  # three out of four events have no campaign
    out: list[tuple[int, int, int, str, dict[str, str]]] = []
    for i in range(len(when)):
        props = {"device": DEVICES[device[i]]}
        if campaign[i] < CAMPAIGNS:
            props["campaign"] = f"c{campaign[i]:02d}"
        out.append((i + 1, int(customer[i]), int(when[i]), EVENT_KINDS[kind[i]], props))
    return out
