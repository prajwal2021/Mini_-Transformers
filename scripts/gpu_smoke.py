"""GPU smoke test: train the 12M model for a few hundred steps on the mock corpus.

Not the real training loop (a later prompt builds that). It checks that tokenizer ->
packing -> model -> AdamW/bf16 works on the GPU, and measures throughput and memory so
pretraining time can be scheduled.

Usage: python scripts/gpu_smoke.py [--steps 300] [--batch-size 32] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.data_loading import PackedDataset  # noqa: E402
from slm.model import ModelConfig, Transformer, count_parameters  # noqa: E402
from slm.tokenizer import read_documents, train_tokenizer  # noqa: E402

MOCK = ROOT / "tests" / "fixtures" / "mock_corpus_train.txt"


def build_data(seq_len: int) -> tuple[PackedDataset, int]:
    tok = train_tokenizer([MOCK], vocab_size=4096, min_frequency=1)
    docs = [tok.encode_document(t) for t in read_documents([MOCK])]
    return PackedDataset([d[:-1] for d in docs], seq_len=seq_len), tok.vocab_size


def batches(ds: PackedDataset, batch_size: int, device, seed: int = 0):
    """Endless stream of full batches (cycles epochs; the mock set is tiny)."""
    epoch = 0
    while True:
        for b in ds.epoch(batch_size, epoch=epoch, seed=seed, drop_last=True):
            yield {k: v.to(device, non_blocking=True) for k, v in b.items()}
        epoch += 1


def train(steps: int, batch_size: int, use_compile: bool, seed: int = 0, lr: float = 6e-4) -> dict:
    device = torch.device("cuda")
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    cfg = ModelConfig.from_yaml(ROOT / "configs" / "model.yaml")
    ds, vocab = build_data(cfg.context_len)
    assert vocab == cfg.vocab_size
    torch.manual_seed(seed)
    model = Transformer(cfg).to(device).train()
    run = torch.compile(model) if use_compile else model
    decay = [p for p in model.parameters() if p.ndim >= 2]
    no_decay = [p for p in model.parameters() if p.ndim < 2]
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 0.1}, {"params": no_decay, "weight_decay": 0.0}],
        lr=lr, betas=(0.9, 0.95), fused=True,
    )
    stream = batches(ds, batch_size, device, seed)
    warm, losses, grad_norms = 10, [], []
    torch.cuda.reset_peak_memory_stats()
    t0 = None
    for step in range(steps):
        if step == warm:
            torch.cuda.synchronize()
            t0 = time.perf_counter()
        for g in opt.param_groups:
            g["lr"] = lr * min(1.0, (step + 1) / 30)
        b = next(stream)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            _, loss = run(b["input_ids"], doc_ids=b["doc_ids"], labels=b["labels"])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        grad_norms.append(torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0))
        opt.step()
        losses.append(loss.detach())
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0
    timed_steps = steps - warm
    losses = [float(x) for x in losses]
    positions = batch_size * cfg.context_len * timed_steps
    return {
        "compile": use_compile,
        "batch_size": batch_size,
        "steps": steps,
        "positions_per_s": positions / elapsed,
        "real_tokens_per_s": positions * ds.efficiency / elapsed,
        "step_time_ms": 1000 * elapsed / timed_steps,
        "peak_mem_gb": torch.cuda.max_memory_allocated() / 2**30,
        "loss_start": losses[0],
        "loss_end": losses[-1],
        "loss_min": min(losses),
        "finite": all(map(lambda x: x == x and abs(x) < 1e6, losses)),
        "grad_norm_max": float(max(grad_norms)),
        "packing_efficiency": ds.efficiency,
        "n_sequences": len(ds),
        "n_params": count_parameters(model),
    }


def probe_batch_sizes(sizes=(16, 32, 64, 96)) -> list[dict]:
    out = []
    for bs in sizes:
        try:
            r = train(14, bs, use_compile=False)
            out.append({"batch_size": bs, "peak_mem_gb": r["peak_mem_gb"], "ok": True})
        except torch.cuda.OutOfMemoryError:
            out.append({"batch_size": bs, "ok": False})
            break
        finally:
            torch.cuda.empty_cache()
    return out


def estimate(r: dict, tokens: float = 1e6, epochs: int = 20, efficiency: float | None = None):
    eff = efficiency or r["packing_efficiency"]
    seconds = tokens * epochs / eff / r["positions_per_s"]
    return seconds / 60


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--skip-probe", action="store_true")
    args = ap.parse_args()
    if not torch.cuda.is_available():
        sys.exit("CUDA is not available")
    report = {
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "bf16": torch.cuda.is_bf16_supported(),
        "total_mem_gb": torch.cuda.get_device_properties(0).total_memory / 2**30,
    }
    print(report)
    if not args.skip_probe:
        report["batch_probe"] = probe_batch_sizes()
        print("batch probe:", report["batch_probe"])
    report["eager"] = train(args.steps, args.batch_size, use_compile=False)
    print("eager:", report["eager"])
    try:
        report["compiled"] = train(args.steps, args.batch_size, use_compile=True)
        print("compiled:", report["compiled"])
    except Exception as exc:  # Triton is unavailable on native Windows
        report["compiled"] = {"error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"}
        print("torch.compile failed:", report["compiled"]["error"])
        traceback.print_exc(limit=2)
    e = report["eager"]
    report["estimate_minutes_1M_tokens_x20_epochs"] = {
        "at_mock_packing_efficiency": estimate(e),
        "at_90pct_packing_efficiency": estimate(e, efficiency=0.9),
    }
    print("estimate (min), 1M tokens x 20 epochs:", report["estimate_minutes_1M_tokens_x20_epochs"])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
