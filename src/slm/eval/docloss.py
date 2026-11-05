"""Document-level LM loss for val/test documents, by document regime and style cell.

``nll_fn(text) -> (total_nll, n_tokens)`` is injected, so this needs no model or tokenizer.
``regime`` here is the DOCUMENT-level iid/novel regime of the plan (``style_regime``), not the
probe frame. Cells follow D-024: the novel regime holds out author_role (quality auditor, route
editor) or tone (apologetic). DESIGN.md itself does not define role/tone cells.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

import pandas as pd

NllFn = Callable[[str], tuple[float, int]]

HELD_OUT_ROLES = ("quality auditor", "route editor")
HELD_OUT_TONES = ("apologetic",)

COLUMNS = ["split", "regime", "group_by", "group", "n_docs", "n_tokens", "mean_nll"]


def attach_texts(plan_rows: Iterable[Mapping], texts: Mapping[str, str]) -> list[dict]:
    """Join plan rows (doc_id, split, style_regime, style_card) with generated texts."""
    return [{**r, "text": texts[r["doc_id"]]} for r in plan_rows if r["doc_id"] in texts]


def doc_loss_by_regime(nll_fn: NllFn, docs: Iterable[Mapping]) -> pd.DataFrame:
    """Mean per-token NLL (token-weighted: total NLL / total tokens) for val and test documents.

    Rows: per split x regime ("all"), and per split x regime x author_role / tone / held_out_style.
    Train documents are ignored.
    """
    acc: dict[tuple[str, str, str, str], list[float]] = {}

    def add(key: tuple[str, str, str, str], nll: float, n: int) -> None:
        a = acc.setdefault(key, [0.0, 0, 0])
        a[0] += nll
        a[1] += n
        a[2] += 1

    for d in docs:
        split, regime = d["split"], d["style_regime"]
        if split not in ("val", "test"):
            continue
        nll, n = nll_fn(d["text"])
        card = d["style_card"]
        held = card["author_role"] in HELD_OUT_ROLES or card["tone"] in HELD_OUT_TONES
        add((split, regime, "all", "all"), nll, n)
        add((split, regime, "author_role", card["author_role"]), nll, n)
        add((split, regime, "tone", card["tone"]), nll, n)
        add((split, regime, "held_out_style", "yes" if held else "no"), nll, n)

    rows = [
        {
            "split": s, "regime": r, "group_by": g, "group": v, "n_docs": tot[2],
            "n_tokens": tot[1], "mean_nll": tot[0] / tot[1] if tot[1] else float("nan"),
        }
        for (s, r, g, v), tot in sorted(acc.items())
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
