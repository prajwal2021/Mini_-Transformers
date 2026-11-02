"""Train fact-to-document assignment: constructive fill plus constrained local search.

Hard constraints preserved by every move (P1, P2):
  * every fact keeps exactly ``planned_mentions`` documents (swaps only exchange facts),
  * no document holds two facts of one attribute (or one fact twice),
  * a document spans at most two families, and at most ``cross_share`` of the documents are
    cross-family (every pair of families shares a compatible document type).

Objective, in order: maximum pair count, pairs above three, sum of squared pair counts.
When the bin-independence target is missed, a second phase trades sum of squares for bin
balance while holding the maximum pair count at the cap.
"""

from __future__ import annotations

import itertools
import random
from collections import Counter, defaultdict
from typing import Any

BINS = ("high", "mid", "low")
BIN_PAIRS = [(a, b) for a in range(3) for b in range(a, 3)]
PAIR_CAP = 6
RATIO_LOW, RATIO_HIGH = 0.75, 1.25


def family_sizes(
    family_slots: dict[str, int], attrs_per_family: dict[str, int], n1: int, n3: int
) -> dict[str, tuple[int, int, int]]:
    """Split the global (n1, n2, n3) document mix into per-family (k1, k2, k3) counts."""
    families = sorted(family_slots)
    wide = [f for f in families if attrs_per_family[f] >= 3]
    wide_slots = sum(family_slots[f] for f in wide)
    k3 = {f: 0 for f in families}
    for f in wide:
        k3[f] = round(n3 * family_slots[f] / wide_slots)
    k3[wide[-1]] += n3 - sum(k3.values())
    rest = {f: family_slots[f] - 3 * k3[f] for f in families}
    total_rest = sum(rest.values())
    k1 = {}
    for f in families:
        target = n1 * rest[f] / total_rest
        k1[f] = max(0, round((target - rest[f] % 2) / 2) * 2 + rest[f] % 2)
    drift = n1 - sum(k1.values())
    adjust = max(families, key=lambda f: rest[f])
    k1[adjust] += drift
    assert k1[adjust] >= 0 and k1[adjust] % 2 == rest[adjust] % 2, "k1 parity repair failed"
    return {f: (k1[f], (rest[f] - k1[f]) // 2, k3[f]) for f in families}


def _initial_docs(
    facts: list[dict[str, Any]], sizes: dict[str, tuple[int, int, int]], rng: random.Random
) -> list[list[int]]:
    """Gale-Ryser style fill: place each attribute's mentions into the roomiest documents."""
    docs: list[list[int]] = []
    for family in sorted(sizes):
        k1, k2, k3 = sizes[family]
        slots = [1] * k1 + [2] * k2 + [3] * k3
        contents: list[list[int]] = [[] for _ in slots]
        by_attr: dict[str, list[int]] = defaultdict(list)
        for index, fact in enumerate(facts):
            if fact["family"] == family:
                by_attr[fact["attribute_id"]].extend([index] * fact["planned_mentions"])
        for attribute, values in sorted(by_attr.items(), key=lambda item: (-len(item[1]), item[0])):
            rng.shuffle(values)
            order = sorted(
                range(len(slots)),
                key=lambda s: (-(slots[s] - len(contents[s])), rng.random()),
            )
            chosen = [s for s in order if slots[s] > len(contents[s])][: len(values)]
            assert len(chosen) == len(values), f"cannot place {attribute} in {family}"
            for s, value in zip(chosen, values):
                contents[s].append(value)
        assert all(len(c) == k for c, k in zip(contents, slots))
        docs.extend(contents)
    return docs


class _Search:
    """Incremental pair-count state and swap local search."""

    def __init__(
        self, facts: list[dict[str, Any]], docs: list[list[int]], cross_cap: int, rng: random.Random
    ) -> None:
        self.facts, self.docs, self.rng, self.cross_cap = facts, docs, rng, cross_cap
        self.n = len(facts)
        self.fam = [f["family"] for f in facts]
        self.attr = [f["attribute_id"] for f in facts]
        self.bin = [BINS.index(f["freq_bin"]) for f in facts]
        self.cnt = [0] * (self.n * self.n)
        self.hist = [0] * 64
        self.mx = self.sumsq = self.n3 = 0
        self.bc = [0] * len(BIN_PAIRS)
        self.bidx = {pair: i for i, pair in enumerate(BIN_PAIRS)}
        self.bidx.update({(b, a): i for (a, b), i in list(self.bidx.items())})
        self.endpoints = [0, 0, 0]
        self.total_pairs = sum(len(d) * (len(d) - 1) // 2 for d in docs)
        self.ncross = 0
        self.nfam = [len({self.fam[x] for x in d}) for d in docs]
        self.ncross = sum(1 for c in self.nfam if c > 1)
        for d in docs:
            for a, b in itertools.combinations(d, 2):
                self._inc(a, b)
            for x in d:
                self.endpoints[self.bin[x]] += len(d) - 1

    def _inc(self, a: int, b: int) -> None:
        key = a * self.n + b if a < b else b * self.n + a
        c = self.cnt[key]
        if c:
            self.hist[c] -= 1
        c += 1
        self.cnt[key] = c
        self.hist[c] += 1
        self.sumsq += 2 * c - 1
        if c == 4:
            self.n3 += 1
        if c > self.mx:
            self.mx = c
        self.bc[self.bidx[(self.bin[a], self.bin[b])]] += 1

    def _dec(self, a: int, b: int) -> None:
        key = a * self.n + b if a < b else b * self.n + a
        c = self.cnt[key]
        self.hist[c] -= 1
        self.cnt[key] = c - 1
        if c > 1:
            self.hist[c - 1] += 1
        self.sumsq -= 2 * c - 1
        if c == 4:
            self.n3 -= 1
        if c == self.mx and self.hist[c] == 0:
            self.mx = c - 1
        self.bc[self.bidx[(self.bin[a], self.bin[b])]] -= 1

    def ratios(self) -> list[float]:
        total = sum(self.endpoints)
        share = [e / total for e in self.endpoints]
        out = []
        for i, (a, b) in enumerate(BIN_PAIRS):
            expected = self.total_pairs * share[a] * share[b] * (1 if a == b else 2)
            out.append(self.bc[i] / expected if expected else 0.0)
        return out

    def penalty(self) -> int:
        return int(
            1e4 * sum(max(0.0, abs(r - 1.0) - 0.2) ** 2 for r in self.ratios())
        )

    def key(self, phase: int) -> tuple[int, ...]:
        if phase == 1:
            return (self.mx, self.n3, self.sumsq)
        return (max(0, self.mx - PAIR_CAP), self.penalty(), self.n3, self.sumsq)

    def _swap(self, i: int, p: int, j: int, q: int) -> None:
        di, dj = self.docs[i], self.docs[j]
        a, b = di[p], dj[q]
        for x in di:
            if x != a:
                self._dec(a, x)
                self._inc(b, x)
        for x in dj:
            if x != b:
                self._dec(b, x)
                self._inc(a, x)
        self.endpoints[self.bin[a]] += len(dj) - len(di)
        self.endpoints[self.bin[b]] += len(di) - len(dj)
        di[p], dj[q] = b, a
        for index, d in ((i, di), (j, dj)):
            fresh = len({self.fam[x] for x in d})
            self.ncross += (fresh > 1) - (self.nfam[index] > 1)
            self.nfam[index] = fresh

    def _legal(self, i: int, p: int, j: int, q: int) -> bool:
        di, dj = self.docs[i], self.docs[j]
        a, b = di[p], dj[q]
        if a == b or b in di or a in dj:
            return False
        ai, aj = self.attr[a], self.attr[b]
        if any(x != a and self.attr[x] == aj for x in di):
            return False
        if any(x != b and self.attr[x] == ai for x in dj):
            return False
        fi = {self.fam[x] for x in di if x != a} | {self.fam[b]}
        fj = {self.fam[x] for x in dj if x != b} | {self.fam[a]}
        if len(fi) > 2 or len(fj) > 2:
            return False
        after = (
            self.ncross
            + (len(fi) > 1)
            + (len(fj) > 1)
            - (self.nfam[i] > 1)
            - (self.nfam[j] > 1)
        )
        return after <= self.cross_cap

    def hot_docs(self, threshold: int) -> list[int]:
        hot = []
        for index, d in enumerate(self.docs):
            for a, b in itertools.combinations(d, 2):
                key = a * self.n + b if a < b else b * self.n + a
                if self.cnt[key] >= threshold:
                    hot.append(index)
                    break
        return hot

    def run(self, phase: int, iterations: int, trace: list[dict[str, Any]], every: int) -> None:
        rng = self.rng
        ndocs = len(self.docs)
        current = self.key(phase)
        hot: list[int] = []
        accepted = 0
        for step in range(1, iterations + 1):
            if (step - 1) % 1000 == 0:
                hot = self.hot_docs(max(self.mx, PAIR_CAP + 1) if phase == 2 else self.mx)
            if step % every == 0 or step == 1:
                trace.append(
                    {
                        "phase": phase,
                        "step": step,
                        "max_pair": self.mx,
                        "pairs_above_3": self.n3,
                        "sum_sq": self.sumsq,
                        "cross_docs": self.ncross,
                        "ratio_min": round(min(self.ratios()), 3),
                        "ratio_max": round(max(self.ratios()), 3),
                    }
                )
            if hot and rng.random() < 0.5:
                i = rng.choice(hot)
            else:
                i = rng.randrange(ndocs)
            j = rng.randrange(ndocs)
            if j == i:
                continue
            p = rng.randrange(len(self.docs[i]))
            q = rng.randrange(len(self.docs[j]))
            if not self._legal(i, p, j, q):
                continue
            self._swap(i, p, j, q)
            proposal = self.key(phase)
            if proposal <= current:
                current = proposal
                accepted += 1
            else:
                self._swap(i, p, j, q)


def bin_table(search: _Search) -> list[dict[str, Any]]:
    """Observed/expected co-occurrence counts for each unordered bin pair."""
    total = sum(search.endpoints)
    share = [e / total for e in search.endpoints]
    rows = []
    for i, (a, b) in enumerate(BIN_PAIRS):
        expected = search.total_pairs * share[a] * share[b] * (1 if a == b else 2)
        rows.append(
            {
                "bins": f"{BINS[a]} x {BINS[b]}",
                "observed": search.bc[i],
                "expected": round(expected, 1),
                "ratio": round(search.bc[i] / expected, 3) if expected else None,
            }
        )
    return rows


def capacity_rows(facts: list[dict[str, Any]], cap: int, cross: bool) -> list[dict[str, Any]]:
    """Distinct admissible fact pairs per bin pair times the pair cap."""
    totals: Counter[tuple[int, int]] = Counter()
    for (x, fx), (y, fy) in itertools.combinations(enumerate(facts), 2):
        if fx["attribute_id"] == fy["attribute_id"]:
            continue
        if not cross and fx["family"] != fy["family"]:
            continue
        a, b = sorted((BINS.index(fx["freq_bin"]), BINS.index(fy["freq_bin"])))
        totals[(a, b)] += 1
    return [
        {"bins": f"{BINS[a]} x {BINS[b]}", "pairs": totals[(a, b)], "capacity": totals[(a, b)] * cap}
        for a, b in BIN_PAIRS
    ]


def _attempt(
    facts: list[dict[str, Any]],
    sizes: dict[str, tuple[int, int, int]],
    seed: int,
    cross_cap: int,
    iters: tuple[int, int],
) -> tuple[_Search, dict[str, Any]]:
    rng = random.Random(seed)
    docs = _initial_docs(facts, sizes, rng)
    rng.shuffle(docs)
    search = _Search(facts, docs, cross_cap, rng)
    trace: list[dict[str, Any]] = []
    initial = {"max_pair": search.mx, "pairs_above_3": search.n3, "sum_sq": search.sumsq}
    search.run(1, iters[0], trace, every=max(1, iters[0] // 5))
    after_phase1 = {"max_pair": search.mx, "pairs_above_3": search.n3, "sum_sq": search.sumsq}
    ratios_after_1 = [round(r, 3) for r in search.ratios()]
    ran_phase2 = not all(RATIO_LOW <= r <= RATIO_HIGH for r in ratios_after_1)
    if ran_phase2:
        search.run(2, iters[1], trace, every=max(1, iters[1] // 5))
    info = {
        "cross_cap": cross_cap,
        "initial": initial,
        "after_phase1": after_phase1,
        "ratios_after_phase1": ratios_after_1,
        "phase2_run": ran_phase2,
        "final": {"max_pair": search.mx, "pairs_above_3": search.n3, "sum_sq": search.sumsq},
        "trace": trace,
        "bin_table": bin_table(search),
        "cross_docs": search.ncross,
        "endpoints": dict(zip(BINS, search.endpoints)),
        "total_pairs": search.total_pairs,
    }
    return search, info


def meets_targets(info: dict[str, Any]) -> bool:
    return info["final"]["max_pair"] <= PAIR_CAP and all(
        RATIO_LOW <= row["ratio"] <= RATIO_HIGH for row in info["bin_table"]
    )


def assign_train(
    facts: list[dict[str, Any]],
    mix: dict[str, int],
    seed: int,
    cross_shares: tuple[float, ...] = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35),
    iters: tuple[int, int] = (300_000, 500_000),
) -> tuple[list[list[int]], dict[str, Any]]:
    """Return per-document fact-index lists and diagnostics.

    The cross-family allowance is raised step by step; the first value that meets P3' and the
    bin-independence target is used. If none does, the largest allowance is kept.
    """
    family_slots: Counter[str] = Counter()
    attrs: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        family_slots[fact["family"]] += fact["planned_mentions"]
        attrs[fact["family"]].add(fact["attribute_id"])
    sizes = family_sizes(
        dict(family_slots), {f: len(a) for f, a in attrs.items()}, mix["k1"], mix["k3"]
    )
    ndocs = mix["k1"] + mix["k2"] + mix["k3"]
    escalation = []
    chosen: tuple[_Search, dict[str, Any]] | None = None
    for share in cross_shares:
        search, info = _attempt(facts, sizes, seed, int(share * ndocs), iters)
        escalation.append(
            {
                "cross_share_allowed": share,
                "cross_docs_used": info["cross_docs"],
                "max_pair": info["final"]["max_pair"],
                "pairs_above_3": info["final"]["pairs_above_3"],
                "sum_sq": info["final"]["sum_sq"],
                "ratio_min": min(r["ratio"] for r in info["bin_table"]),
                "ratio_max": max(r["ratio"] for r in info["bin_table"]),
                "met": meets_targets(info),
            }
        )
        chosen = (search, info)
        if meets_targets(info):
            break
    assert chosen is not None
    search, info = chosen
    info.update(
        {
            "sizes": sizes,
            "escalation": escalation,
            "capacity_within_family": capacity_rows(facts, PAIR_CAP, cross=False),
            "capacity_cross_family": capacity_rows(facts, PAIR_CAP, cross=True),
            "targets_met": meets_targets(info),
        }
    )
    return search.docs, info
