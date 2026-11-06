"""Re-run marker insertion (repair v2), validator v5 and the artifact detector on stored raw model outputs.

No API calls: every stored attempt keeps ``raw_text`` (the model output with markers). The original
attempts file is kept once as attempts_v7_original.jsonl; the reprocessed attempts replace
attempts.jsonl so that scripts/run_corpus.py can resume from them. Attempts after the first accepted
one of a document are dropped from the new file (they were only made because of the old repair).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from slm.data.artifacts import has_artifact
from slm.data.pilot import _load_attempts, _safe
from slm.data.versions import normaliser_for, process_response, prompt_tools, validator_for

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-mini"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "corpus" / "raw")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "tables" / "corpus_reprocess_run2.md")
    args = parser.parse_args(argv)
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    pools = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
    plan = {r["doc_id"]: r for r in (json.loads(x) for x in
            (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines())}
    path = args.raw_dir / _safe(MODEL) / "attempts.jsonl"
    backup = path.with_name("attempts_v7_original.jsonl")
    if not backup.exists():
        shutil.copy2(path, backup)
    original = _load_attempts(backup)
    tools = prompt_tools("v8", MODEL)
    validate, normalise = validator_for("v5"), normaliser_for("v5")
    by_doc: dict[str, list[dict]] = {}
    for a in original:
        by_doc.setdefault(a["doc_id"], []).append(a)
    out: list[dict] = []
    stats = Counter()
    changed_docs, newly_ok, newly_failed, dropped_attempts = [], [], [], 0
    artifacts_before = artifacts_after = 0
    for doc_id, attempts in by_doc.items():
        row = plan[doc_id]
        previous_rules = None
        was_ok = any(a["ok"] for a in attempts)
        final_old = next((a for a in attempts if a["ok"]), None)
        final_new = None
        for a in sorted(attempts, key=lambda x: x["attempt"]):
            processed = process_response(tools, validate, normalise, a["raw_text"], row, kb, pools)
            rule_set = frozenset(m.group(0) for r in processed["reasons"] if (m := re.match(r"V\d+[bp]?", r)))
            stuck = bool(not processed["ok"] and rule_set and rule_set == previous_rules)
            previous_rules = rule_set
            new = {**a, "ok": processed["ok"], "reasons": processed["reasons"], "text": processed["text"],
                   "placements": processed["placements"], "stuck": stuck, "reprocessed": "repair_v2"}
            out.append(new)
            if processed["ok"]:
                final_new = new
                break
            if stuck:
                break
        dropped_attempts += len(attempts) - sum(1 for x in out if x["doc_id"] == doc_id)
        if final_old is not None and row["fact_ids"]:
            artifacts_before += has_artifact(final_old["text"])
        if final_new is not None and row["fact_ids"]:
            artifacts_after += has_artifact(final_new["text"])
        if final_new is not None and final_old is not None and final_new["text"] != final_old["text"]:
            changed_docs.append(doc_id)
        if final_new is not None and not was_ok:
            newly_ok.append(doc_id)
        if final_new is None and was_ok:
            newly_failed.append(doc_id)
        for f, p in (final_new or {}).get("placements", {}).items():
            stats[(row["doc_type"], p["placement"])] += 1
    # a document that was accepted before but fails under repair v2 is regenerated from scratch on resume
    out = [x for x in out if x["doc_id"] not in set(newly_failed)]
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")
    bearing = sum(1 for d, atts in by_doc.items() if plan[d]["fact_ids"] and any(a["ok"] for a in atts))
    lines = ["# Reprocessing of the run-2 raw outputs with marker repair v2 (no API calls)", "",
             f"Documents: {len(by_doc)}; attempts before {len(original)}, after {len(out)} "
             f"(dropped {dropped_attempts} attempts that followed the first accepted one).",
             f"Accepted documents whose text changed: {len(changed_docs)}.",
             f"Documents accepted now but not before: {len(newly_ok)} {newly_ok}.",
             f"Documents accepted before but failing now: {len(newly_failed)} {newly_failed} (their attempts are removed "
             "from attempts.jsonl and the documents are regenerated with prompt v8 on resume).",
             f"Mention-bearing accepted documents with an artifact: before {artifacts_before}, after {artifacts_after} "
             f"(of {bearing} before).", "", "| doc type | model | repaired_missing | repaired_mid_v2 | repaired_dup |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for t in sorted({k[0] for k in stats}):
        lines.append(f"| {t} | " + " | ".join(str(stats[(t, p)]) for p in ("model", "repaired_missing", "repaired_mid_v2", "repaired_dup")) + " |")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
