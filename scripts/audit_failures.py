# ruff: noqa: E501
"""R07 D2: raw format-failure outputs. (a) the existing E0 TEST predictions (text only: re-decoding test prompts is not allowed);
(b) fresh decodes of SFT TRAIN questions with token ids and the stop reason (train split only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.generation import generate_text, newline_token_ids  # noqa: E402
from slm.model import load_checkpoint  # noqa: E402
from slm.sft_eval import Taxonomy, load_attribute_values  # noqa: E402
from slm.sft_eval.evaluate import clean_prediction, occurs  # noqa: E402
from slm.tokenizer import BPETokenizer  # noqa: E402

out = {}
q = pd.read_csv(ROOT / "runs/real/qa/qa_predictions.csv")
e0 = q[(q.eval_set == "E0") & (q.checkpoint == "sft") & (q.error_class == "format_failure")].sample(10, random_state=1)
out["a_existing_test_predictions_E0_sft_format_failure"] = [
    {"question_id": r.question_id, "seed": int(r.seed), "gold": r.gold, "prediction": r.prediction, "n_words": len(str(r.prediction).split())} for r in e0.itertuples()]
print("(a) existing E0 SFT format_failure predictions (test; text only)")
for r in out["a_existing_test_predictions_E0_sft_format_failure"]:
    print(r)
print("share of E0 SFT format_failure that are empty:", float((q[(q.eval_set == 'E0') & (q.checkpoint == 'sft') & (q.error_class == 'format_failure')].prediction.fillna('').str.strip() == '').mean()))
print("what format_failure means in the code: empty, OR degenerate repetition, OR no value-like string of the attribute's type (taxonomy.py)")

dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tok = BPETokenizer.load(ROOT / "runs/real/tokenizer.json")
av = load_attribute_values(ROOT / "data/kb/kb.json")
tax = Taxonomy.from_kb(ROOT / "data/kb/kb.json")
rows = [json.loads(x) for x in (ROOT / "data/sft/sft_train.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
stop = newline_token_ids(tok)
res = []
for name, ck in (("sft best.pt (seed 0, epoch 1)", "runs/real/sft/seed0/checkpoints/best.pt"), ("sft epoch_003 (seed 0)", "runs/real/sft/seed0/checkpoints/epoch_003.pt")):
    m = load_checkpoint(ROOT / ck, map_location=dev).to(dev).eval()
    fails = []
    for r in rows:
        text, gen = generate_text(m, tok, r["prompt"], 48, stop, dev)
        pred = clean_prediction(text)
        ok = occurs(pred, r["value"]) and not any(occurs(pred, v) for v in av[r["attribute_id"]] if v != r["value"])
        if not ok:
            cls = tax.classify(pred, r["attribute_id"], r["value"], False)
            fails.append({"id": r["id"], "gold": r["answer"], "decoded": text, "token_ids": gen.token_ids[:30], "stopped": gen.stopped, "eos_produced": gen.stopped == "eos", "n_generated": len(gen.token_ids), "class": cls})
    print(f"\n(b) {name}: {len(fails)}/{len(rows)} train questions not exact; classes", pd.Series([f['class'] for f in fails]).value_counts().to_dict(), "stopped", pd.Series([f['stopped'] for f in fails]).value_counts().to_dict())
    ff = [f for f in fails if f["class"] == "format_failure"][:10] or fails[:10]
    for f in ff:
        print(f)
    res.append({"checkpoint": name, "n_not_exact": len(fails), "examples": ff})
out["b_train_question_decodes"] = res
Path(ROOT / "reports/integration/r07/format_failures.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
