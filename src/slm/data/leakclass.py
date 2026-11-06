"""Leak classification (P02c5): classes of the 13-grams shared by val/test documents with train."""

from __future__ import annotations

from collections import defaultdict

from . import corpus
from .bank import BankStore

GRAM = corpus.GRAM


def signoff_start(text: str) -> int | None:
    """Token index where the sign-off line (last line) starts, or None."""
    lines = [x for x in text.split("\n") if x.strip()]
    last = lines[-1].strip().lower().rstrip(",.")
    if len(lines) > 1 and last.endswith("companion animal travel desk") and len(last.split()) <= 8:
        return len(corpus.tokens("\n".join(lines[:-1])))
    return None


def analyse(docs: list[dict], plan_by_id: dict, kb: dict) -> dict:
    store = BankStore.load()
    train = defaultdict(set)
    for d in docs:
        if d["split"] == "train":
            for g in corpus.grams13(d["text"]):
                train[g].add(d["doc_id"])
    info: dict = {}
    for d in docs:
        if d["split"] == "train":
            continue
        toks = corpus.tokens(d["text"])
        sign = signoff_start(d["text"])
        facts = []
        if d["fact_ids"]:
            facts = [corpus.tokens(v["text"]) for v in store.inserted(plan_by_id[d["doc_id"]], kb).values()]
        fact_grams = {tuple(f[i:i + GRAM]) for f in facts for i in range(max(0, len(f) - GRAM + 1))}
        for i in range(len(toks) - GRAM + 1):
            g = tuple(toks[i:i + GRAM])
            if g not in train:
                continue
            rec = info.setdefault(g, {"docs": set(), "types": set(), "sign": 0, "inside": 0, "n": 0, "fact": False})
            rec["docs"].add(d["doc_id"])
            rec["types"].add(d["doc_type"])
            rec["n"] += 1
            if sign is not None and i + GRAM > sign:
                rec["sign"] += 1
                if i >= sign:
                    rec["inside"] += 1
            rec["fact"] = rec["fact"] or bool(fact_grams & {g})
    for g, rec in info.items():
        rec["train_docs"] = len(train[g])
        if rec["inside"] == rec["n"] and rec["n"]:
            rec["class"] = "i"
        elif rec["sign"]:
            rec["class"] = "i-b"
        elif rec["train_docs"] >= 3 and not rec["fact"]:
            rec["class"] = "ii"
        else:
            rec["class"] = "iii"
    return info


def exempt_docs(info: dict) -> set[str]:
    """Docs whose every shared gram is class (i)."""
    bad: dict[str, bool] = {}
    for rec in info.values():
        for d in rec["docs"]:
            bad[d] = bad.get(d, False) or rec["class"] != "i"
    return {d for d, v in bad.items() if v}
