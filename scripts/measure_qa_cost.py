# ruff: noqa: E501
"""R04: cost of the QA evaluation (greedy generation) on this machine, and the projection for the real run.

    python scripts/measure_qa_cost.py [--ckpt runs/real_mock/pretrain/seed0/checkpoints/epoch_002.pt]
        [--tokenizer runs/real_mock/tokenizer.json] [--n 72] [--limit-minutes 40]

Times unbatched greedy decoding (the harness's ``generate_text``: stop at a newline token, at most 48 new tokens) on
the SFT *validation* questions (``data/sft/sft_val.jsonl``; the QA test file is never opened here), zero-shot and with
the 2-shot base prefix. Projection: questions x 3 variants (pretrained zero-shot, pretrained 2-shot, SFT zero-shot) x
seeds, plus the ranking scoring. R04 rule: batched left-padded greedy decoding is added only if the projection exceeds
``--limit-minutes``; it did not (see reports/integration/REPORT_BACK_R04.md), so there is no batched decoder.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--ckpt", default=str(ROOT / "runs" / "real_mock" / "pretrain" / "seed0" / "checkpoints" / "epoch_002.pt"))
    ap.add_argument("--tokenizer", default=str(ROOT / "runs" / "real_mock" / "tokenizer.json"))
    ap.add_argument("--n", type=int, default=72)
    ap.add_argument("--questions", type=int, default=660)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--limit-minutes", type=float, default=40.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    from slm.generation import generate_text, newline_token_ids
    from slm.model import load_checkpoint
    from slm.model.transformer import count_parameters
    from slm.sft_eval import load_base_prompts, prompt_prefixes
    from slm.tokenizer import BPETokenizer

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tok = BPETokenizer.load(args.tokenizer)
    model = load_checkpoint(args.ckpt, map_location=dev).to(dev).eval()
    rows = [json.loads(x) for x in (ROOT / "data" / "sft" / "sft_val.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()][: args.n]
    rows = (rows * (args.n // max(len(rows), 1) + 1))[: args.n]  # sft_val has only 24 rows: repeat them to time args.n answers
    pre = prompt_prefixes(load_base_prompts(ROOT / "configs" / "base_prompts.yaml"))
    stop = newline_token_ids(tok)
    res: dict = {"device": str(dev), "gpu": torch.cuda.get_device_name(0) if dev.type == "cuda" else None,
                 "params": count_parameters(model), "n_questions_timed": len(rows), "test_file_opened": False}

    def timed(fn, prompts):
        if dev.type == "cuda":
            torch.cuda.synchronize()
        t = time.perf_counter()
        out = fn(prompts)
        if dev.type == "cuda":
            torch.cuda.synchronize()
        return out, time.perf_counter() - t

    def unbatched(prompts):
        return [generate_text(model, tok, p, 48, stop, dev)[0] for p in prompts]

    unbatched([rows[0]["prompt"]])  # warm-up (CUDA init, kernels)
    per = {}
    outs = {}
    for mode in ("zero_shot", "2shot"):
        prompts = [pre[mode] + r["prompt"] for r in rows]
        outs[mode], secs = timed(unbatched, prompts)
        per[mode] = secs / len(rows)
        res[f"unbatched_{mode}_s_per_answer"] = round(per[mode], 4)
    from slm.eval_adapter import ModelScorer
    from slm.sft_eval import load_attribute_values
    from slm.sft_eval.ranking import rank_rows

    av = load_attribute_values(ROOT / "data" / "kb" / "kb.json")
    ranker = ModelScorer(model, tok, dev)
    rank_rows(ranker, rows[:2], av, "")
    _, rsecs = timed(lambda _: rank_rows(ranker, rows, av, pre["2shot"]), None)
    res["ranking_s_per_question_2shot"] = round(rsecs / len(rows), 4)
    n = args.questions * args.seeds
    total = n * (2 * per["zero_shot"] + per["2shot"])  # pretrained zero-shot + SFT zero-shot + pretrained 2-shot
    res["projection"] = {"questions": args.questions, "variants": 3, "seeds": args.seeds, "answers": args.questions * 3 * args.seeds,
                         "unbatched_minutes": round(total / 60, 1), "limit_minutes": args.limit_minutes,
                         "exceeds_limit": (total + n * 3 * rsecs / len(rows)) / 60 > args.limit_minutes,
                         "ranking_minutes_all_variants": round(n * 3 * rsecs / len(rows) / 60, 1),
                         "total_minutes_unbatched": round((total + n * 3 * rsecs / len(rows)) / 60, 1),
                         "note": "answers = questions x 3 variants x seeds; ranking time is extra (ranking=True in st_qa_eval)"}
    print(json.dumps(res, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
