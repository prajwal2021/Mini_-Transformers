# ruff: noqa: E501
"""R07 D: audit of the SFT evaluation on sft_train / sft_val ONLY (never the QA test file, no test decode).

    python scripts/audit_sft.py [--run runs/real] [--out reports/integration/r07/sft_audit.json]

1. exact_value_match (the evaluator's own code path: evaluate_checkpoint, greedy, 48 tokens) on the SFT TRAIN questions and
   on sft_val, for every saved SFT checkpoint of every seed (epoch_001.., best.pt);
2. teacher-forced loss and mean answer log-prob on train and val (answer tokens + eos only, as in training);
3. a checkpoint / eos / tokenisation consistency report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def rows_of(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@torch.no_grad()
def teacher_forced(model, tok, rows, dev) -> dict:
    from slm.sft_train.data import collate, encode_rows

    exs = encode_rows(tok, rows, model.cfg.context_len)
    tot, n, lps = 0.0, 0, []
    for i in range(0, len(exs), 16):
        b = {k: v.to(dev) for k, v in collate(exs[i:i + 16]).items()}
        out = model(b["input_ids"], doc_ids=b["doc_ids"])
        logits = out[0] if isinstance(out, tuple) else out
        ce = F.cross_entropy(logits.reshape(-1, logits.size(-1)).float(), b["labels"].reshape(-1), ignore_index=-100, reduction="none").reshape(b["labels"].shape)
        m = b["labels"] != -100
        tot += float(ce[m].sum())
        n += int(m.sum())
        for j in range(ce.size(0)):
            lps.append(-float(ce[j][m[j]].sum()))
    return {"loss_per_answer_token": round(tot / n, 4), "mean_answer_logprob": round(sum(lps) / len(lps), 3), "n_answer_tokens": n}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default=str(ROOT / "runs" / "real"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    a = ap.parse_args(argv)
    from slm.model import load_checkpoint
    from slm.sft_eval import evaluate_checkpoint, load_attribute_values
    from slm.tokenizer import BPETokenizer

    run = Path(a.run)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tok = BPETokenizer.load(run / "tokenizer.json")
    av = load_attribute_values(ROOT / "data" / "kb" / "kb.json")
    train, val = rows_of(ROOT / "data" / "sft" / "sft_train.jsonl"), rows_of(ROOT / "data" / "sft" / "sft_val.jsonl")
    res: dict = {"files_read": ["data/sft/sft_train.jsonl", "data/sft/sft_val.jsonl"], "qa_test_opened": False, "rows": []}
    for seed in a.seeds:
        d = run / "sft" / f"seed{seed}"
        summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        for name in ["epoch_001", "epoch_002", "epoch_003", "best"]:
            p = d / "checkpoints" / f"{name}.pt"
            if not p.exists():
                continue
            model = load_checkpoint(p, map_location=dev).to(dev).eval()
            row = {"seed": seed, "ckpt": name, "best_epoch_in_summary": summ["best_epoch"], "training": model.training}
            for split, rows in (("train", train), ("val", val)):
                t = evaluate_checkpoint(p, tok, rows, seed, av, dev, 48, label=name, model=model)
                row[f"{split}_exact_value_match"] = round(float(t["exact_value_match"].mean()), 4)
                row[f"{split}_contains_gold"] = round(float(t["contains_gold"].mean()), 4)
                row[f"{split}_sentence_exact"] = round(float(t["sentence_exact"].mean()), 4)
                row.update({f"{split}_tf_{k}": v for k, v in teacher_forced(model, tok, rows, dev).items() if k != "n_answer_tokens"})
                if split == "train" and name == "best" and seed == 0:
                    t.to_csv(Path(a.out).with_name("sft_train_predictions_seed0_best.csv") if a.out else run / "sft_train_pred.csv", index=False)
            res["rows"].append(row)
            print(row)
    df = pd.DataFrame(res["rows"])
    print(df.to_string())
    ex = rows_of(ROOT / "data" / "sft" / "sft_train.jsonl")[0]
    p_ids, a_ids = tok.encode(f"Question: {ex['question']}\nAnswer:"), tok.encode(f" {ex['answer']}")
    joint = tok.encode(f"Question: {ex['question']}\nAnswer: {ex['answer']}")
    res["tokenisation_boundary_equal_to_joint"] = joint == p_ids + a_ids
    res["eos_id"] = tok.eos_id
    res["val_fact_overlap_with_train"] = sorted({r["fact_id"] for r in val} & {r["fact_id"] for r in train})
    res["n_val_facts"] = len({r["fact_id"] for r in val})
    print({k: v for k, v in res.items() if k != "rows"})
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
