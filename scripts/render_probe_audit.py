# ruff: noqa: E501
"""Render the probe prompts of the real KB (R00 1): checks all 480 and prints 24 covering every attribute.

    python scripts/render_probe_audit.py [--out reports/integration/probe_rendering_R00.md]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from slm.eval.wording import CANONICAL, article, prefix

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("canon", "n1", "n2", "n3")


def problems(prompt: str, value: str) -> list[str]:
    bad = []
    if prompt != prompt.strip() or "  " in prompt:
        bad.append("whitespace")
    if not prompt[0].isupper():
        bad.append("capital")
    if re.search(r"\b(\w+)\s+\1\b", prompt, flags=re.I):
        bad.append("doubled word")
    if any(m.group(1).lower() != article(m.group(2)) for m in re.finditer(r"\b(a|an)\s+([A-Za-z][\w'-]*)", prompt, flags=re.I)):
        bad.append("a/an")
    if value.lower() in prompt.lower():
        bad.append("contains value")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kb", default=str(ROOT / "data" / "kb" / "kb.json"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "integration" / "probe_rendering_R00.md"))
    args = ap.parse_args(argv)
    facts = json.loads(Path(args.kb).read_text(encoding="utf-8"))["measured_facts"]
    n_bad, shown = 0, []
    for f in facts:
        for v in VARIANTS:
            p = prefix(f["attribute_id"], v, f["entity"])
            n_bad += bool(problems(p, f["value"]))
    for i, attr in enumerate(CANONICAL):  # one fact per attribute, variants rotate; a/an cases first
        f = next(x for x in facts if x["attribute_id"] == attr)
        shown.append((attr, f, VARIANTS[i % 4]))
    for i, ent in enumerate(("reptile", "rabbit", "bird", "large dog")):  # more a-cases, other species
        f = next(x for x in facts if x["entity"] == ent and x["attribute_id"].startswith("species_"))
        shown.append((f["attribute_id"], f, VARIANTS[(i + 1) % 4]))
    shown = shown[:24]
    lines = [f"# Probe rendering audit (R00): {len(facts)} facts x 4 wordings = {len(facts) * 4} prompts, "
             f"{n_bad} with a problem", "", "| # | fact | attribute | wording | rendered prompt | + value |", "|---|---|---|---|---|---|"]
    for i, (attr, f, v) in enumerate(shown, 1):
        lines.append(f"| {i} | {f['fact_id']} | {attr} | {v} | {prefix(attr, v, f['entity'])} | {f['value']} |")
    text = "\n".join(lines) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
