"""The generator needs no database: it must be repeatable and its rows must be consistent."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from sqlshow import datagen
from sqlshow.datagen import Dataset, generate


def test_same_seed_same_rows_other_seed_other_rows() -> None:
    assert generate(0.02, 7) == generate(0.02, 7)
    assert generate(0.02, 7) != generate(0.02, 8)


def test_sizes_scale_and_have_a_floor() -> None:
    big, tiny = datagen.sizes(1.0), datagen.sizes(0.0001)
    assert (big.customers, big.products, big.orders, big.events) == (20_000, 2_000, 200_000, 500_000)
    assert (tiny.customers, tiny.products, tiny.orders, tiny.events) == (200, 120, 2_000, 5_000)
    with pytest.raises(ValueError, match="positive"):
        datagen.sizes(0)


def test_keys_are_unique_and_foreign_keys_resolve(data: Dataset) -> None:
    categories = {c[0] for c in data.categories}
    products = {p[0] for p in data.products}
    customers = {c[0] for c in data.customers}
    orders = {o[0] for o in data.orders}
    assert len(categories) == len(data.categories) == 85
    assert len(products) == len(data.products) and len(customers) == len(data.customers)
    assert len(orders) == len(data.orders)
    assert all(parent is None or parent in categories for _, parent, _ in data.categories)
    leaves = {c[0] for c in data.categories} - {c[1] for c in data.categories if c[1] is not None}
    assert all(p[1] in leaves for p in data.products)
    assert all(o[1] in customers for o in data.orders)
    assert all(i[0] in orders and i[2] in products for i in data.order_items)
    assert all(e[1] in customers for e in data.events)
    assert len({(i[0], i[1]) for i in data.order_items}) == len(data.order_items)
    assert len({e[0] for e in data.events}) == len(data.events)


def test_no_product_twice_in_an_order_and_every_order_has_lines(data: Dataset) -> None:
    per_order: dict[int, list[int]] = {}
    for oid, _, pid, qty, unit in data.order_items:
        per_order.setdefault(oid, []).append(pid)
        assert 1 <= qty <= 5 and unit > 0
    assert set(per_order) == {o[0] for o in data.orders}
    assert all(len(set(p)) == len(p) for p in per_order.values())


def test_ids_follow_time(data: Dataset) -> None:
    times = [o[2] for o in data.orders]
    assert times == sorted(times)
    events = [e[2] for e in data.events]
    assert events == sorted(events)
    assert times[0] >= datagen.START_EPOCH and times[-1] < datagen.END_EPOCH and events[-1] < datagen.END_EPOCH


def test_pending_orders_are_recent_only(data: Dataset) -> None:
    cutoff = datagen.END_EPOCH - datagen.PENDING_DAYS * 86400
    pending = [o for o in data.orders if o[3] == "pending"]
    assert pending and all(o[2] >= cutoff for o in pending)
    assert set(Counter(o[3] for o in data.orders)) == {"paid", "shipped", "refunded", "cancelled", "pending"}


def test_customers_and_events_have_the_shapes_the_queries_need(data: Dataset) -> None:
    assert all(c[1].lower() == f"user{c[0]}@example.com" for c in data.customers)
    assert any(c[1] != c[1].lower() for c in data.customers)  # mixed case exists, for the expression index
    assert all(isinstance(c[3], date) for c in data.customers)
    assert any("campaign" in e[4] for e in data.events) and any("campaign" not in e[4] for e in data.events)
    assert {e[3] for e in data.events} == set(datagen.EVENT_KINDS)


def test_formatting_helpers() -> None:
    assert datagen.cents(12345) == "123.45" and datagen.cents(5) == "0.05" and datagen.cents(100) == "1.00"
    assert datagen.timestamp(datagen.START_EPOCH) == "2023-01-01 00:00:00+00:00"
    assert datagen.props_json({"b": "1", "a": "2"}) == '{"a": "2", "b": "1"}'
