# ruff: noqa: E501
"""R06: held-out (validation) loss per checkpoint, on all val documents and excluding the flagged ones.

    python scripts/heldout_loss.py --run runs/real --out reports/integration/heldout_loss_R06.json

PREREG v5 section 10 item 9: validation documents flagged ``leak_flag`` or ``meta_flag`` in the corpus manifest
(val-0031, val-0047, val-0070, val-0085, val-0112) are excluded in the second number. Only the VAL split is read, never test.
Loss = mean next-token cross-entropy over the tokens of each document (document + <|eos|>, truncated to the context),
pooled over documents; one number per (seed, epoch). It is computed per document, so it differs slightly from the
packed validation loss of the training log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def flagged_val_ids(manifest: dict) -> list[str]:
    ids = {k for k in manifest.get("leak_flag", {}) if k.startswith("val-")}
    ids |= {k for k in manifest.get("meta_flag", []) if k.startswith("val-")}
    return sorted(ids)


@torch.no_grad()
def doc_losses(model, token_docs: list[list[int]], dev) -> list[tuple[float, int]]:
    """(sum of token NLL, number of predicted tokens) per document."""
    out = []
    for ids in token_docs:
        x = torch.tensor([ids[:-1]], device=dev)
        y = torch.tensor([ids[1:]], device=dev)
        logits = model(x)
        logits = logits[0] if isinstance(logits, tuple) else logits
        out.append((float(F.cross_entropy(logits[0], y[0], reduction="sum")), y.numel()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--run", default=str(ROOT / "runs" / "real"))
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus"))
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--epochs", type=int, nargs="+", default=[12, 30, 60])
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    from slm.integration.probing import list_checkpoints
    from slm.model import load_checkpoint
    from slm.tokenizer import BPETokenizer

    run, corpus = Path(args.run), Path(args.corpus)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    flagged = flagged_val_ids(manifest)
    docs = [json.loads(x) for x in (corpus / "val.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert all(d["split"] == "val" for d in docs)
    tok = BPETokenizer.load(run / "tokenizer.json")
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ids = [d["doc_id"] for d in docs]
    missing = [f for f in flagged if f not in ids]
    if missing:
        raise SystemExit(f"flagged ids not in val.jsonl: {missing}")
    keep = [i for i, d in enumerate(ids) if d not in set(flagged)]
    res: dict = {"flagged_val_docs": flagged, "n_val_docs": len(docs), "n_without_flagged": len(keep), "split_read": "val", "loss": {}}
    for seed in args.seeds:
        by_epoch = {e: p for _, e, p in list_checkpoints(run / "pretrain" / f"seed{seed}")}
        for ep in args.epochs:
            model = load_checkpoint(by_epoch[ep], map_location=dev).to(dev).eval()
            ctx = model.cfg.context_len if hasattr(model, "cfg") else 512
            td = [tok.encode_document(d["text"])[: ctx + 1] for d in docs]
            L = doc_losses(model, td, dev)
            tot = lambda idx: sum(L[i][0] for i in idx) / sum(L[i][1] for i in idx)  # noqa: E731
            res["loss"][f"seed{seed}_epoch{ep}"] = {"all_val_docs": round(tot(range(len(docs))), 4),
                                                    "without_flagged": round(tot(keep), 4)}
    print(json.dumps(res, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
