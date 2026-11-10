"""The expected answer of every query, computed in plain Python from the generated rows (no SQL, no database).

If a SQL query and its reference agree, the query does what its comment says, written twice in two languages.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np

from sqlshow.datagen import Dataset

VALID = ("paid", "shipped")
REFERENCE_DATE = date(2026, 1, 1)


def dec(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def rnd(x: Decimal, places: int = 2) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def when(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def month_of(epoch: int) -> date:
    t = when(epoch)
    return date(t.year, t.month, 1)


def month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


class Reference:
    def __init__(self, data: Dataset) -> None:
        self.data = data
        self.order = {o[0]: o for o in data.orders}
        self.category_of = {p[0]: p[1] for p in data.products}
        # one row per line of a paid or shipped order: (order, customer, time, product, category, quantity, cents)
        self.sales = [
            (oid, self.order[oid][1], self.order[oid][2], pid, self.category_of[pid], qty, qty * unit)
            for oid, _, pid, qty, unit in data.order_items
            if self.order[oid][3] in VALID
        ]
        self.valid_orders = sum(1 for o in data.orders if o[3] in VALID)

    def q01(self) -> list[tuple[Any, ...]]:
        revenue: Counter[tuple[int, int]] = Counter()
        for _, _, _, pid, cat, _, amount in self.sales:
            revenue[(cat, pid)] += amount
        by_cat: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for (cat, pid), r in revenue.items():
            by_cat[cat].append((-r, pid))
        rows = []
        for cat in sorted(by_cat):
            for rank, (neg, pid) in enumerate(sorted(by_cat[cat])[:3], start=1):
                rows.append((cat, rank, pid, dec(-neg)))
        return rows

    def q02(self) -> list[tuple[Any, ...]]:
        monthly: Counter[date] = Counter()
        for _, _, ts, _, _, _, amount in self.sales:
            monthly[month_of(ts)] += amount
        months = sorted(monthly)
        rows = []
        for i, m in enumerate(months):
            prev = monthly[months[i - 1]] if i else None
            growth = None if not prev else rnd(100 * (Decimal(monthly[m]) - Decimal(prev)) / Decimal(prev))
            window = [monthly[x] for x in months[max(0, i - 2) : i + 1]]
            rows.append(
                (
                    m,
                    dec(monthly[m]),
                    None if prev is None else dec(prev),
                    growth,
                    rnd(Decimal(sum(window)) / Decimal(len(window)) / 100),
                )
            )
        return rows

    def q03(self) -> list[tuple[Any, ...]]:
        active: dict[int, set[date]] = defaultdict(set)
        for o in self.data.orders:
            if o[3] in VALID:
                active[o[1]].add(month_of(o[2]))
        cohort_of = {c: min(ms) for c, ms in active.items()}
        size = Counter(cohort_of.values())
        counts: Counter[tuple[date, int]] = Counter()
        for c, ms in active.items():
            for m in ms:
                offset = month_index(m) - month_index(cohort_of[c])
                if 0 <= offset <= 11:
                    counts[(cohort_of[c], offset)] += 1
        return [
            (cohort, off, n, size[cohort], rnd(100 * Decimal(n) / Decimal(size[cohort])))
            for (cohort, off), n in sorted(counts.items())
        ]

    @staticmethod
    def ntile(keys: dict[int, tuple[Any, ...]], buckets: int = 5) -> dict[int, int]:
        order = sorted(keys, key=lambda c: keys[c])
        base, extra = divmod(len(order), buckets)
        out: dict[int, int] = {}
        pos = 0
        for b in range(1, buckets + 1):
            for c in order[pos : pos + base + (1 if b <= extra else 0)]:
                out[c] = b
            pos += base + (1 if b <= extra else 0)
        return out

    def q04(self) -> list[tuple[Any, ...]]:
        last: dict[int, int] = {}
        orders: dict[int, set[int]] = defaultdict(set)
        money: Counter[int] = Counter()
        for oid, cust, ts, _, _, _, amount in self.sales:
            last[cust] = max(last.get(cust, 0), ts)
            orders[cust].add(oid)
            money[cust] += amount
        recency = {c: (REFERENCE_DATE - when(ts).date()).days for c, ts in last.items()}
        r = self.ntile({c: (-recency[c], c) for c in last})
        f = self.ntile({c: (len(orders[c]), c) for c in last})
        m = self.ntile({c: (money[c], c) for c in last})
        groups: dict[str, list[int]] = defaultdict(list)
        for c in last:
            if r[c] >= 4 and f[c] >= 4 and m[c] >= 4:
                seg = "champions"
            elif r[c] >= 4:
                seg = "recent"
            elif f[c] >= 4:
                seg = "loyal"
            elif r[c] <= 2 and m[c] >= 4:
                seg = "big spenders at risk"
            elif r[c] <= 2:
                seg = "at risk"
            else:
                seg = "regular"
            groups[seg].append(c)
        return [
            (
                seg,
                len(cs),
                rnd(Decimal(sum(money[c] for c in cs)) / Decimal(len(cs)) / 100),
                rnd(Decimal(sum(len(orders[c]) for c in cs)) / Decimal(len(cs))),
            )
            for seg, cs in groups.items()
        ]

    def q05(self) -> list[tuple[Any, ...]]:
        revenue: Counter[int] = Counter()
        for _, _, _, pid, _, _, amount in self.sales:
            revenue[pid] += amount
        total = sum(revenue.values())
        rows = []
        running = 0
        for pid, r in sorted(revenue.items(), key=lambda kv: (-kv[1], kv[0])):
            running += r
            klass = "A" if running * 5 <= total * 4 else "B" if running * 100 <= total * 95 else "C"
            rows.append((pid, dec(r), rnd(100 * Decimal(running) / Decimal(total)), klass))
        return rows

    def q06(self) -> list[tuple[Any, ...]]:
        children: dict[int | None, list[int]] = defaultdict(list)
        name = {}
        for cid, parent, nm in self.data.categories:
            children[parent].append(cid)
            name[cid] = nm
        own: Counter[int] = Counter()
        for _, _, _, _, cat, _, amount in self.sales:
            own[cat] += amount
        rows = []

        def walk(cid: int, path: str, depth: int) -> int:
            total = own[cid]
            for child in children[cid]:
                total += walk(child, f"{path} > {name[child]}", depth + 1)
            rows.append((depth, cid, path, dec(own[cid]), dec(total)))
            return total

        for root in children[None]:
            walk(root, name[root], 0)
        return [(cid, path, depth, o, t) for depth, cid, path, o, t in sorted(rows)]

    def q07(self) -> list[tuple[Any, ...]]:
        per: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for eid, cust, ts, _, _ in self.data.events:
            per[cust].append((ts, eid))
        sessions = []
        for cust, evs in per.items():
            evs.sort()
            number, start, prev, n = 0, evs[0][0], None, 0
            for ts, _ in evs:
                if prev is None or ts - prev > 1800:
                    if prev is not None:
                        sessions.append((cust, number, start, prev, n))
                    number += 1
                    start, n = ts, 0
                n += 1
                prev = ts
            sessions.append((cust, number, start, prev, n))
        top = sorted(sessions, key=lambda s: (-s[4], s[2], s[0]))[:20]
        return [(c, no, when(a), when(b), n, b - a) for c, no, a, b, n in top]

    def q08(self) -> list[tuple[Any, ...]]:
        days: dict[int, set[date]] = defaultdict(set)
        for _, cust, ts, _, _ in self.data.events:
            days[cust].add(when(ts).date())
        best = []
        for cust, ds in days.items():
            run = sorted(ds)
            streaks: list[tuple[int, date, date]] = []
            start = prev = run[0]
            for d in run[1:]:
                if (d - prev).days != 1:
                    streaks.append(((prev - start).days + 1, start, prev))
                    start = d
                prev = d
            streaks.append(((prev - start).days + 1, start, prev))
            days_n, first, last = min(streaks, key=lambda s: (-s[0], s[1]))
            best.append((cust, days_n, first, last))
        return sorted(best, key=lambda r: (-r[1], r[2], r[0]))[:10]

    def q09(self) -> list[tuple[Any, ...]]:
        value: Counter[int] = Counter()
        for oid, _, _, qty, unit in self.data.order_items:
            value[oid] += qty * unit
        country = {c[0]: c[2] for c in self.data.customers}
        by: dict[str, list[float]] = defaultdict(list)
        refunded: Counter[str] = Counter()
        for oid, cust, _, status in self.data.orders:
            by[country[cust]].append(value[oid] / 100)
            refunded[country[cust]] += status == "refunded"
        rows = []
        for ctry, vals in by.items():
            rows.append(
                (
                    ctry,
                    len(vals),
                    *(float(np.percentile(vals, p)) for p in (50, 90, 99)),
                    rnd(100 * Decimal(refunded[ctry]) / Decimal(len(vals))),
                )
            )
        return rows

    def q10(self) -> list[tuple[Any, ...]]:
        items: dict[int, list[int]] = defaultdict(list)
        for oid, _, pid, _, _ in self.data.order_items:
            if self.order[oid][3] in VALID:
                items[oid].append(pid)
        pairs: Counter[tuple[int, int]] = Counter()
        for products in items.values():
            for i, a in enumerate(products):
                for b in products[i + 1 :]:
                    pairs[(min(a, b), max(a, b))] += 1
        top = sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
        return [(a, b, n, rnd(100 * Decimal(n) / Decimal(self.valid_orders), 3)) for (a, b), n in top]

    def q11(self) -> list[tuple[Any, ...]]:
        revenue: Counter[int] = Counter()
        totals: dict[int, Counter[int]] = defaultdict(Counter)
        for oid, cust, _, _, _, _, amount in self.sales:
            revenue[cust] += amount
            totals[cust][oid] += amount
        rows = []
        for cust, _ in sorted(revenue.items(), key=lambda kv: (-kv[1], kv[0]))[:5]:
            last = sorted(totals[cust], key=lambda o: (-self.order[o][2], -o))[:3]
            for rn, oid in enumerate(last, start=1):
                rows.append((cust, rn, oid, when(self.order[oid][2]), dec(totals[cust][oid])))
        return rows

    def q12(self) -> list[tuple[Any, ...]]:
        country = {c[0]: c[2] for c in self.data.customers}
        detail: Counter[tuple[int, str]] = Counter()
        orders: dict[tuple[int, str], set[int]] = defaultdict(set)
        for oid, cust, ts, _, _, _, amount in self.sales:
            key = (when(ts).year, country[cust])
            detail[key] += amount
            orders[key].add(oid)
        rows: list[tuple[Any, ...]] = [(y, c, dec(r), len(orders[(y, c)]), 0) for (y, c), r in detail.items()]
        for year in {y for y, _ in detail}:
            keys = [k for k in detail if k[0] == year]
            rows.append(
                (year, None, dec(sum(detail[k] for k in keys)), len(set().union(*(orders[k] for k in keys))), 1)
            )
        rows.append((None, None, dec(sum(detail.values())), len(set().union(*orders.values())), 3))
        return rows

    def q13(self) -> list[tuple[Any, ...]]:
        first: dict[int, tuple[int, int, int]] = {}
        for oid, cust, ts, pid, _, _, _ in self.sales:
            cand = (ts, oid, pid)
            if cust not in first or cand < first[cust]:
                first[cust] = cand
        counts = Counter(self.category_of[pid] for _, _, pid in first.values())
        return sorted(((cat, n) for cat, n in counts.items()), key=lambda r: (-r[1], r[0]))
