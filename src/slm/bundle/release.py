# ruff: noqa: E501
"""R09 release bundle: explicit, named models (not a seed-selection rule) plus the report, the key tables and the configs.

    bundle/
      pretrained/          seed 0, E* = 30 (the primary analysis checkpoint)
      sft_early_stopped/   seed 0, the PRE-SPECIFIED primary SFT (early stopping on the SFT-validation loss)
      sft_fixed3/          seed 0, the POST-HOC secondary SFT (fixed 3 epochs, no early stopping)
      configs/  report/  results/
      MANIFEST.json        sha256 and size of every file in the bundle
      CHECKPOINTS.md  README_BUNDLE.md  requirements.txt

Each model directory is a normal ``slm.bundle`` bundle (``load_bundle`` / ``scripts/generate.py`` read it), with ``variant`` and
``description`` added to its ``bundle_manifest.json``. Nothing here is read from .env, the corpus or the API logs.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import torch

from slm.model import ModelConfig, Transformer, count_parameters, save_checkpoint
from slm.tokenizer import BPETokenizer

from .bundle import (
    BUNDLE_FILES,
    FORMAT_VERSION,
    MANIFEST,
    BundleError,
    _git,
    requirements_text,
    sha256_file,
)


@dataclass(frozen=True)
class Entry:
    name: str  # directory name
    kind: str  # "pretrained" | "sft"
    source: Path
    variant: str | None
    description: str


def _rel(path: Path) -> str:
    """Path relative to the repository (no local user name in the manifest)."""
    p = Path(path).resolve()
    parts = p.parts
    return Path(*parts[parts.index("runs"):]).as_posix() if "runs" in parts else p.name


def build_model_dir(entry: Entry, tokenizer_path: Path, out: Path, seed: int) -> dict:
    tok = BPETokenizer.load(tokenizer_path)
    blob = torch.load(entry.source, map_location="cpu", weights_only=True)
    cfg = ModelConfig.from_dict(blob["config"])
    if tok.vocab_size != cfg.vocab_size:
        raise BundleError(f"{entry.source}: model vocab {cfg.vocab_size} != tokenizer {tok.vocab_size}")
    model = Transformer(cfg)
    model.load_state_dict(blob["state_dict"])
    d = out / entry.name
    d.mkdir(parents=True, exist_ok=True)
    save_checkpoint(model, d / "model.pt")  # config + state_dict only
    (d / "tokenizer.json").write_bytes(Path(tokenizer_path).read_bytes())
    (d / "model_config.json").write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    manifest = {
        "format_version": FORMAT_VERSION, "kind": entry.kind, "variant": entry.variant, "description": entry.description, "seed": seed,
        "files": {n: sha256_file(d / n) for n in BUNDLE_FILES},
        "source_checkpoint": _rel(entry.source), "source_sha256": sha256_file(entry.source),
        "selection": {"rule": "explicit (R09): seed 0; checkpoint named in the description", "val_loss_by_seed": {}},
        "git": _git(), "torch": torch.__version__, "n_params": count_parameters(model), "model_config": cfg.to_dict(),
        "tokenizer_hash": tok.hash(), "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (d / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def copy_files(pairs: list[tuple[Path, Path]]) -> list[str]:
    done = []
    for src, dst in pairs:
        if not src.is_file():
            raise BundleError(f"missing file to bundle: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        done.append(dst.as_posix())
    return done


def top_manifest(out: Path) -> dict:
    files = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            files[p.relative_to(out).as_posix()] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    return {"format": "release bundle R09", "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "total_bytes": sum(v["bytes"] for v in files.values()), "files": files}


def verify_top_manifest(out: str | Path) -> list[str]:
    """Problems found when re-hashing every file listed in ``MANIFEST.json`` (empty list = intact)."""
    out = Path(out)
    m = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    bad = []
    for name, rec in m["files"].items():
        p = out / name
        if not p.is_file():
            bad.append(f"missing: {name}")
        elif sha256_file(p) != rec["sha256"]:
            bad.append(f"changed: {name}")
    listed = set(m["files"])
    for p in out.rglob("*"):
        if p.is_file() and p.name != "MANIFEST.json" and p.relative_to(out).as_posix() not in listed:
            bad.append(f"unlisted: {p.relative_to(out).as_posix()}")
    return bad


def checkpoints_md(entries: list[Entry], mans: dict[str, dict], sizes: dict[str, int]) -> str:
    rows = "\n".join(f"| `{e.name}/` | {e.kind} | {e.variant or '-'} | {mans[e.name]['n_params']:,} | {sizes[e.name] / 2**20:.1f} MiB | {e.description} |" for e in entries)
    return f"""# Checkpoints in this bundle

All three come from **seed 0** of the final runs (three seeds were trained; the others are not bundled). Weights only; no optimizer state.

| directory | kind | variant | parameters | size | what it is |
|---|---|---|---|---|---|
{rows}

**Which SFT is which.** `sft_early_stopped` is the **pre-specified primary** SFT: early stopping on the loss of a 12-fact SFT-validation set, which
selected epoch 1 for seed 0 (so it is a lightly trained model). `sft_fixed3` is a **post-hoc secondary** SFT added after the results were seen
(fixed 3 epochs, no early stopping, otherwise the same configuration); it answers the training facts far better but is not the pre-specified result.
The report's primary numbers are for `sft_early_stopped`; the fixed-3 numbers are labelled post-hoc.

Each directory has `model.pt`, `tokenizer.json` (the same file in all three), `model_config.json` and `bundle_manifest.json` (sha256 of the three
files, git commit, parameter count). `MANIFEST.json` at the top lists the sha256 of every file in the bundle; `scripts/make_bundle.py --verify bundle`
re-checks it, and `scripts/generate.py` checks the per-model hashes at every load.
"""


def readme_text() -> str:
    return """# Release bundle

Run the models without retraining (CPU is enough). From the repository root, with `requirements.txt` installed:

    python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who manages the pet lounge at Caldreth?"
    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Caldreth opens at"
    python scripts/generate.py --bundle-root bundle --compare --qa "Who manages the pet lounge at Caldreth?"

Contents: see `CHECKPOINTS.md` (which model is which; the early-stopped SFT is the pre-specified primary, the fixed-3 SFT is a post-hoc secondary),
`MANIFEST.json` (sha256 of every file), `configs/` (model, training, SFT and run configuration), `report/report.pdf` and `results/` (key tables,
including the original and corrected H1/H2 numbers). No API keys, `.env`, raw corpus or generation logs are included.
"""


def build_release(
    out_dir: str | Path,
    tokenizer_path: str | Path,
    entries: list[Entry],
    extras: list[tuple[Path, Path]],
    seed: int = 0,
) -> dict:
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    mans = {e.name: build_model_dir(e, Path(tokenizer_path), out, seed) for e in entries}
    sizes = {e.name: sum(f.stat().st_size for f in (out / e.name).iterdir()) for e in entries}
    copy_files([(s, out / d) for s, d in extras])
    (out / "requirements.txt").write_text(requirements_text(), encoding="utf-8")
    (out / "CHECKPOINTS.md").write_text(checkpoints_md(entries, mans, sizes), encoding="utf-8")
    (out / "README_BUNDLE.md").write_text(readme_text(), encoding="utf-8")
    top = top_manifest(out)
    (out / "MANIFEST.json").write_text(json.dumps(top, indent=1), encoding="utf-8")
    return {"models": {n: {"bytes": sizes[n], "n_params": mans[n]["n_params"], "source": mans[n]["source_checkpoint"]} for n in mans},
            "total_bytes": sum(p.stat().st_size for p in out.rglob("*") if p.is_file()), "n_files": len(top["files"]) + 1}
