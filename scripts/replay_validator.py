"""Offline replay of the stored pilot attempts through validator v1 and v2 (no API calls).

Every stored attempt text is normalised first (typography only), then validated by the frozen v1
and by v2. Writes reports/tables/pilot_replay.md.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from slm.data import doc_validator, doc_validator_v1, doc_validator_v2
from slm.data.insertion import substitute

ROOT = Path(__file__).resolve().parents[1]
RULE = re.compile(r"V\d+b?(?:/V\d+)?")
BINS = [("0-5", 0, 5), ("6-10", 6, 10), ("11-15", 11, 15), ("16-25", 16, 25), ("26+", 26, 10**6)]


def rules_of(reasons: list[str]) -> list[str]:
    seen: list[str] = []
    for reason in reasons:
        match = RULE.match(reason)
        key = match.group(0) if match else "other"
        if key not in seen:
            seen.append(key)
    return seen


def table(header: list[str], body: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |"
              for row in body]
    return lines


def load(pilot_dir: Path, kb: dict[str, Any], pools: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows = {
        r["doc_id"]: r
        for r in (json.loads(x) for x in
                  (pilot_dir / "pilot_rows.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for sub in sorted(p for p in pilot_dir.iterdir() if (p / "attempts.jsonl").exists()):
        records = []
        for line in (sub / "attempts.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            a = json.loads(line)
            a["row"] = rows[a["doc_id"]]
            a["empty"] = not a["text"].strip()
            a["clean"] = doc_validator_v2.normalise_text(a["text"])
            if not a["empty"]:
                a["v1_ok"], a["v1_reasons"] = doc_validator_v1.validate_doc(
                    a["clean"], a["row"], kb, pools
                )
                a["v2_ok"], a["v2_reasons"] = doc_validator_v2.validate_doc(
                    a["clean"], a["row"], kb, pools
                )
                a["v1_rules"] = rules_of(a["v1_reasons"])
                a["v2_rules"] = rules_of(a["v2_reasons"])
            records.append(a)
        out[sub.name] = sorted(records, key=lambda a: (a["doc_id"], a["attempt"]))
    return out


def build(data: dict[str, list[dict[str, Any]]], kb: dict[str, Any]) -> str:
    models = list(data)
    lines = [
        "# Pilot replay: validator v1 vs v2",
        "",
        "All stored pilot attempts (prompt v2, reasoning low, P02b2 pilot) re-validated offline. "
        "Each attempt is normalised (typography only) and validated on its own, so retry feedback "
        "effects are not simulated. Empty attempts (API-level E1) are excluded from every "
        "validator figure.",
        "",
        "## Summary",
        "",
    ]
    summary = []
    for m in models:
        attempts = data[m]
        usable = [a for a in attempts if not a["empty"]]
        firsts = [a for a in usable if a["attempt"] == 1]
        docs = {a["doc_id"] for a in attempts}
        v1_docs = {a["doc_id"] for a in usable if a["v1_ok"]}
        v2_docs = {a["doc_id"] for a in usable if a["v2_ok"]}
        summary.append([
            m, len(attempts), len(usable), len(attempts) - len(usable),
            sum(a["v1_ok"] for a in usable), sum(a["v2_ok"] for a in usable),
            f"{sum(a['v1_ok'] for a in firsts)}/{len(firsts)} ({sum(a['v1_ok'] for a in firsts) / max(1, len(firsts)):.1%})",
            f"{sum(a['v2_ok'] for a in firsts)}/{len(firsts)} ({sum(a['v2_ok'] for a in firsts) / max(1, len(firsts)):.1%})",
            f"{len(v1_docs)}/{len(docs)}", f"{len(v2_docs)}/{len(docs)}",
        ])
    lines += table(
        ["model", "attempts", "non-empty attempts", "empty attempts", "accepted attempts v1",
         "accepted attempts v2", "first-attempt pass, non-empty v1", "first-attempt pass, non-empty v2",
         "docs with an accepted attempt v1", "docs with an accepted attempt v2"],
        summary,
    )
    lines += ["", "## Exact-rule reason histogram under v2 (non-empty attempts only)", ""]
    hist = {m: Counter() for m in models}
    atts = {m: Counter() for m in models}
    hist_v1 = {m: Counter() for m in models}
    for m in models:
        for a in data[m]:
            if a["empty"]:
                continue
            for r in a["v2_reasons"]:
                hist[m][rules_of([r])[0]] += 1
            for r in set(a["v2_rules"]):
                atts[m][r] += 1
            for r in a["v1_reasons"]:
                hist_v1[m][rules_of([r])[0]] += 1
    rule_ids = sorted({r for m in models for r in list(hist[m]) + list(hist_v1[m])},
                      key=lambda x: (int(re.match(r"V(\d+)", x).group(1)) if x.startswith("V") else 99, x))
    body = []
    for r in rule_ids:
        body.append([r] + [f"{hist_v1[m][r]}" for m in models] + [f"{hist[m][r]} ({atts[m][r]} attempts)" for m in models])
    lines += table(["rule"] + [f"{m} v1 lines" for m in models] + [f"{m} v2 lines (attempts)" for m in models], body)

    lines += ["", "## V2 word distance (same-sentence entity to value, assigned facts, non-empty attempts)", ""]
    for m in models:
        counts: Counter[str] = Counter()
        for a in data[m]:
            if a["empty"]:
                continue
            for d in doc_validator_v2.bind_distances(a["clean"], a["row"], kb):
                if d is None:
                    counts["unbound (no shared sentence)"] += 1
                else:
                    counts[next(n for n, lo, hi in BINS if lo <= d <= hi)] += 1
        order = [n for n, _l, _h in BINS] + ["unbound (no shared sentence)"]
        total = sum(counts.values())
        lines += [f"### {m}", ""]
        lines += table(["word distance", "facts", "share"],
                       [[k, counts[k], f"{counts[k] / max(1, total):.1%}"] for k in order])
        lines.append("")

    flips_ok, flips_bad = {}, {}
    for m in models:
        usable = [a for a in data[m] if not a["empty"]]
        flips_ok[m] = [a for a in usable if not a["v1_ok"] and a["v2_ok"]]
        flips_bad[m] = [a for a in usable if a["v1_ok"] and not a["v2_ok"]]
    lines += ["## Flips", ""]
    lines += table(["model", "fail -> pass (v1 fail, v2 pass)", "pass -> fail (v1 pass, v2 fail)"],
                   [[m, len(flips_ok[m]), len(flips_bad[m])] for m in models])

    lines += ["", "### fail -> pass: up to 3 docs per fixed rule (V2, V5, V8), printed in full", ""]
    for m in models:
        lines += [f"#### {m}", ""]
        for rule in ("V2", "V5", "V8"):
            picks = [a for a in flips_ok[m] if rule in a["v1_rules"]][:3]
            lines.append(f"Rule {rule}: {len([a for a in flips_ok[m] if rule in a['v1_rules']])} flipped attempts")
            for a in picks:
                lines += [
                    "",
                    f"- {a['doc_id']} attempt {a['attempt']} ({a['row']['doc_type']}, target {a['row']['target_words']} words)",
                    f"  - v1 reasons: {a['v1_reasons']}",
                    "  - v2 verdict: PASS",
                    "", "```text", a["clean"], "```",
                ]
            lines.append("")

    lines += ["### pass -> fail: ALL flips", ""]
    causes: dict[str, Counter[str]] = {m: Counter() for m in models}
    for m in models:
        lines += [f"#### {m}", ""]
        if not flips_bad[m]:
            lines += ["(none)", ""]
        for a in flips_bad[m]:
            for rule in a["v2_rules"]:
                causes[m][rule] += 1
            lines += [f"- {a['doc_id']} attempt {a['attempt']} ({a['row']['doc_type']}): v2 rules {a['v2_rules']}"]
            for reason in a["v2_reasons"]:
                lines.append(f"  - {reason}")
            lines.append("")
    lines += ["Pass -> fail flips by cause (a flip counts once per v2 rule it fails):", ""]
    all_rules = sorted({r for m in models for r in causes[m]})
    lines += table(["cause"] + models, [[r] + [causes[m][r] for m in models] for r in all_rules]) if all_rules else ["(no pass -> fail flips)"]

    lines += ["", "## Per-attempt table", ""]
    body = []
    for m in models:
        for a in data[m]:
            body.append([m, a["doc_id"], a["attempt"], "empty" if a["empty"] else ("PASS" if a["v1_ok"] else ",".join(a["v1_rules"])),
                         "empty" if a["empty"] else ("PASS" if a["v2_ok"] else ",".join(a["v2_rules"]))])
    lines += table(["model", "doc_id", "attempt", "v1", "v2"], body)
    return "\n".join(lines) + "\n"


# ---- v3 -> v4 replay of the prompt-v4 pilot (P02b6) ---------------------------------------

RELAXED = ("V11", "V12", "V15", "V1p", "V5", "V8")


def replay_v4(pilot_dir: Path, kb: dict[str, Any], pools: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Stored v3 verdicts versus validator v4 on the stored RAW model text (insertion re-run)."""
    rows = {
        r["doc_id"]: r
        for r in (json.loads(x) for x in
                  (pilot_dir / "pilot_rows.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for sub in sorted(p for p in pilot_dir.iterdir() if (p / "attempts.jsonl").exists()):
        records = []
        for line in (sub / "attempts.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            a = json.loads(line)
            a["row"] = rows[a["doc_id"]]
            a["empty"] = not a["raw_text"].strip()
            if not a["empty"]:
                clean = doc_validator.normalise_text(a["raw_text"])
                text, reasons = substitute(clean, a["row"], kb)
                if reasons:
                    a["v4_ok"], a["v4_reasons"], a["v4_text"] = False, reasons, clean
                else:
                    a["v4_ok"], a["v4_reasons"] = doc_validator.validate_doc(text, a["row"], kb, pools)
                    a["v4_text"] = text
                a["v3_rules"] = rules_of(a["reasons"])
                a["v4_rules"] = rules_of(a["v4_reasons"])
            records.append(a)
        out[sub.name] = sorted(records, key=lambda a: (a["doc_id"], a["attempt"]))
    return out


def build_v4(data: dict[str, list[dict[str, Any]]]) -> tuple[str, dict[str, float]]:
    models = list(data)
    lines = [
        "# Pilot replay: validator v3 vs v4 on the prompt-v4 pilot (data/pilot_v4)",
        "",
        "v3 = the verdict stored when the pilot ran (validator v3, insertion without the trailing-period "
        "rule). v4 = the stored RAW model text, normalised, placeholders re-inserted with the current "
        "insertion code, validated with v4. Each attempt is judged on its own, so retry feedback is not "
        "simulated. Empty attempts are excluded.",
        "",
        "## (a) First-attempt pass on non-empty attempts",
        "",
    ]
    rates: dict[str, float] = {}
    body = []
    for m in models:
        firsts = [a for a in data[m] if not a["empty"] and a["attempt"] == 1]
        v3 = sum(a["ok"] for a in firsts)
        v4 = sum(a["v4_ok"] for a in firsts)
        rates[m] = v4 / max(1, len(firsts))
        body.append([m, len(firsts), f"{v3} ({v3 / len(firsts):.1%})", f"{v4} ({v4 / len(firsts):.1%})",
                     sum(a["ok"] for a in data[m] if not a["empty"]),
                     sum(a["v4_ok"] for a in data[m] if not a["empty"])])
    lines += table(["model", "first attempts", "v3 pass", "v4 pass", "accepted attempts v3", "accepted attempts v4"], body)
    for m in models:
        lines += ["", f"### {m}: first-attempt pass by doc type", ""]
        types = sorted({a["row"]["doc_type"] for a in data[m]})
        body = []
        for t in types:
            firsts = [a for a in data[m] if not a["empty"] and a["attempt"] == 1 and a["row"]["doc_type"] == t]
            if firsts:
                body.append([t, len(firsts), sum(a["ok"] for a in firsts), sum(a["v4_ok"] for a in firsts)])
        lines += table(["doc type", "first attempts", "v3 pass", "v4 pass"], body)

    lines += ["", "## (b) ALL pass -> fail flips (v3 pass, v4 fail)", ""]
    flips = {m: [a for a in data[m] if not a["empty"] and a["ok"] and not a["v4_ok"]] for m in models}
    lines += table(["model", "pass -> fail flips"], [[m, len(flips[m])] for m in models])
    by_rule: dict[str, int] = {}
    for m in models:
        for a in flips[m]:
            for r in a["v4_rules"]:
                by_rule[r] = by_rule.get(r, 0) + 1
    lines += ["", "Flips by v4 rule: " + (", ".join(f"{k} x{v}" for k, v in sorted(by_rule.items())) or "none"), ""]
    for m in models:
        lines += [f"### {m}", ""]
        if not flips[m]:
            lines += ["(none)", ""]
        for a in flips[m]:
            lines.append(f"- {a['doc_id']} attempt {a['attempt']} ({a['row']['doc_type']}): v4 rules {a['v4_rules']}")
            lines += [f"  - {r}" for r in a["v4_reasons"]]
            lines.append("")

    lines += ["## (c) Every V15 reject under v4", ""]
    for m in models:
        lines += [f"### {m}", ""]
        rejects = [(a, r) for a in data[m] if not a["empty"] for r in a["v4_reasons"] if r.startswith("V15")]
        if not rejects:
            lines += ["(none)", ""]
        for a, reason in rejects:
            lines += [f"- {a['doc_id']} attempt {a['attempt']}: {reason}"]
        lines.append("")

    lines += ["## (d) Up to 3 fail -> pass flips per relaxed rule, in full", ""]
    for m in models:
        lines += [f"### {m}", ""]
        for rule in RELAXED:
            flipped = [a for a in data[m] if not a["empty"] and not a["ok"] and a["v4_ok"] and rule in a["v3_rules"]]
            lines.append(f"Rule {rule}: {len(flipped)} flipped attempts")
            for a in flipped[:3]:
                lines += ["", f"- {a['doc_id']} attempt {a['attempt']} ({a['row']['doc_type']}, target {a['row']['target_words']} words)",
                          f"  - v3 reasons: {a['reasons']}", "  - v4 verdict: PASS", "", "```text", a["v4_text"], "```"]
            lines.append("")

    lines += ["## (e) Remaining reason histogram under v4 (non-empty attempts, exact rule ids)", ""]
    hist = {m: {} for m in models}
    atts = {m: {} for m in models}
    for m in models:
        for a in data[m]:
            if a["empty"]:
                continue
            for r in a["v4_reasons"]:
                k = rules_of([r])[0]
                hist[m][k] = hist[m].get(k, 0) + 1
            for k in set(a["v4_rules"]):
                atts[m][k] = atts[m].get(k, 0) + 1
    all_rules = sorted({k for m in models for k in hist[m]}, key=lambda x: (int(re.match(r"V(\d+)", x).group(1)), x))
    lines += table(["rule"] + [f"{m} lines (attempts)" for m in models],
                   [[k] + [f"{hist[m].get(k, 0)} ({atts[m].get(k, 0)})" for m in models] for k in all_rules])
    return "\n".join(lines) + "\n", rates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=ROOT / "data" / "pilot")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "tables" / "pilot_replay.md")
    parser.add_argument("--validator", choices=["v2", "v4"], default="v2")
    args = parser.parse_args(argv)
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    pools = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
    if args.validator == "v4":
        data4 = replay_v4(args.pilot_dir, kb, pools)
        report, rates = build_v4(data4)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        total = sum(len(v) for v in data4.values())
        print(f"Replayed {total} attempts -> {args.out}")
        print("v4 first-attempt pass on non-empty attempts: " + ", ".join(f"{m} {r:.1%}" for m, r in rates.items()))
        return 0
    data = load(args.pilot_dir, kb, pools)
    total = sum(len(v) for v in data.values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(data, kb), encoding="utf-8")
    print(f"Replayed {total} attempts -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
