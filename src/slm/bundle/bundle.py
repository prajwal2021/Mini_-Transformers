# ruff: noqa: E501
"""Release bundle (docs/DESIGN.md section 9: pretrained + SFT checkpoints, tokenizer, config).

One bundle directory per model (``bundle/pretrained``, ``bundle/sft``)::

    model.pt              {"config", "state_dict"} only: no optimizer, loadable with weights_only
    tokenizer.json        the byte-level BPE merge table
    model_config.json     the model hyper-parameters
    bundle_manifest.json  sha256 of the other three files, kind, seed, git commit, torch version,
                          parameter count, how the seed was chosen

``load_bundle`` reads ONLY these files and checks every hash first.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import torch

from slm.model import ModelConfig, Transformer, count_parameters, save_checkpoint
from slm.tokenizer import BPETokenizer

FORMAT_VERSION = 1
BUNDLE_FILES = ("model.pt", "tokenizer.json", "model_config.json")
MANIFEST = "bundle_manifest.json"
KINDS = ("pretrained", "sft")


class BundleError(RuntimeError):
    """A bundle is missing, incomplete, altered or of the wrong kind."""


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class LoadedBundle:
    model: Transformer
    tokenizer: BPETokenizer
    manifest: dict
    path: Path

    @property
    def kind(self) -> str:
        return self.manifest["kind"]


def load_bundle(bundle_dir: str | Path, device: str | torch.device = "cpu") -> LoadedBundle:
    d = Path(bundle_dir)
    if not d.is_dir():
        raise BundleError(f"bundle directory not found: {d}")
    mpath = d / MANIFEST
    if not mpath.is_file():
        hint = ""
        subs = [s.name for s in d.iterdir() if s.is_dir() and (s / MANIFEST).is_file()] \
            if d.is_dir() else []
        if subs:
            hint = f" It contains bundles {sorted(subs)}; pass one of them, e.g. {d / subs[0]}"
        raise BundleError(f"{MANIFEST} is missing in {d}.{hint}")
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BundleError(f"{mpath} is not valid JSON: {e}") from e
    if manifest.get("format_version") != FORMAT_VERSION or manifest.get("kind") not in KINDS:
        raise BundleError(f"{mpath}: unsupported format_version/kind "
                          f"({manifest.get('format_version')!r}, {manifest.get('kind')!r})")
    for name in BUNDLE_FILES:
        f = d / name
        if not f.is_file():
            raise BundleError(f"required file missing from the bundle: {f}")
        want = manifest["files"].get(name)
        if want is None or sha256_file(f) != want:
            raise BundleError(f"{f} does not match its sha256 in {MANIFEST} (file changed or "
                              "corrupted); re-download the bundle")
    cfg = ModelConfig.from_dict(json.loads((d / "model_config.json").read_text(encoding="utf-8")))
    tokenizer = BPETokenizer.load(d / "tokenizer.json")
    if tokenizer.vocab_size != cfg.vocab_size:
        raise BundleError(f"tokenizer has {tokenizer.vocab_size} tokens, the model {cfg.vocab_size}")
    blob = torch.load(d / "model.pt", map_location="cpu", weights_only=True)
    model = Transformer(ModelConfig.from_dict(blob["config"]))
    model.load_state_dict(blob["state_dict"])
    return LoadedBundle(model.to(device).eval(), tokenizer, manifest, d)


def _final_epoch_ckpt(seed_dir: Path) -> Path:
    ckpts = sorted((seed_dir / "checkpoints").glob("epoch_*.pt"))
    if not ckpts:
        raise BundleError(f"no epoch checkpoints in {seed_dir / 'checkpoints'}")
    return ckpts[-1]


def select_seed(pretrain_run: str | Path, sft_run: str | Path, seed: int | None = None) -> dict:
    """Seed to release: the one with the LOWEST pretraining VALIDATION loss at its final
    checkpoint among seeds that also have an SFT run (ties: lower seed). Test results play no
    part. ``seed`` overrides the rule (recorded as such)."""
    pre, sft = Path(pretrain_run), Path(sft_run)
    table = {}
    for sd in sorted(pre.glob("seed*")):
        k = int(sd.name.removeprefix("seed"))
        summary = sd / "summary.json"
        best = sft / f"seed{k}" / "checkpoints" / "best.pt"
        if summary.is_file() and best.is_file():
            table[k] = float(json.loads(summary.read_text(encoding="utf-8"))["final_val_loss"])
    if not table:
        raise BundleError(f"no seed has both {pre}/seed*/summary.json and an SFT best.pt")
    if seed is not None:
        if seed not in table:
            raise BundleError(f"seed {seed} is not available (have {sorted(table)})")
        return {"seed": seed, "rule": "explicit --seed", "val_loss_by_seed": table}
    best_seed = min(table, key=lambda k: (table[k], k))
    return {"seed": best_seed, "rule": "lowest final pretraining validation loss",
            "val_loss_by_seed": table}


def _git() -> dict:
    from slm.train.pretrain import git_info

    return git_info()


def build_bundle(
    pretrain_run: str | Path,
    sft_run: str | Path,
    tokenizer_path: str | Path,
    out_dir: str | Path,
    seed: int | None = None,
) -> dict:
    """Write ``out_dir/pretrained`` and ``out_dir/sft`` plus README_BUNDLE.md and requirements.txt."""
    choice = select_seed(pretrain_run, sft_run, seed)
    k = choice["seed"]
    sources = {
        "pretrained": _final_epoch_ckpt(Path(pretrain_run) / f"seed{k}"),
        "sft": Path(sft_run) / f"seed{k}" / "checkpoints" / "best.pt",
    }
    out = Path(out_dir)
    tok = BPETokenizer.load(tokenizer_path)
    report = {"seed": k, "selection": choice, "bundles": {}}
    for kind, src in sources.items():
        blob = torch.load(src, map_location="cpu", weights_only=True)
        cfg = ModelConfig.from_dict(blob["config"])
        if tok.vocab_size != cfg.vocab_size:
            raise BundleError(f"{src}: model vocab {cfg.vocab_size} != tokenizer {tok.vocab_size}")
        model = Transformer(cfg)
        model.load_state_dict(blob["state_dict"])
        bdir = out / kind
        bdir.mkdir(parents=True, exist_ok=True)
        save_checkpoint(model, bdir / "model.pt")  # config + state_dict, nothing else
        (bdir / "tokenizer.json").write_bytes(Path(tokenizer_path).read_bytes())
        (bdir / "model_config.json").write_text(json.dumps(cfg.to_dict(), indent=2),
                                                encoding="utf-8")
        manifest = {
            "format_version": FORMAT_VERSION, "kind": kind, "seed": k,
            "files": {n: sha256_file(bdir / n) for n in BUNDLE_FILES},
            "source_checkpoint": src.name, "source_sha256": sha256_file(src),
            "selection": {"rule": choice["rule"], "val_loss_by_seed": choice["val_loss_by_seed"]},
            "git": _git(), "torch": torch.__version__, "n_params": count_parameters(model),
            "model_config": cfg.to_dict(), "tokenizer_hash": tok.hash(),
            "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        (bdir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        size = sum(f.stat().st_size for f in bdir.iterdir())
        report["bundles"][kind] = {"dir": str(bdir), "bytes": size, "n_params": manifest["n_params"],
                                   "files": sorted(p.name for p in bdir.iterdir())}
    (out / "requirements.txt").write_text(requirements_text(), encoding="utf-8")
    (out / "README_BUNDLE.md").write_text(readme_text(report), encoding="utf-8")
    report["total_bytes"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return report


def requirements_text() -> str:
    from importlib.metadata import version

    torch_v = version("torch").split("+")[0]
    return (
        "# Pinned runtime requirements for scripts/generate.py (CPU is enough).\n"
        "# CPU-only torch wheel: pip install -r requirements.txt\n"
        "--extra-index-url https://download.pytorch.org/whl/cpu\n"
        f"torch=={torch_v}\n"
        f"regex=={version('regex')}\n"
        f"PyYAML=={version('PyYAML')}\n"
    )


def readme_text(report: dict) -> str:
    sel = report["selection"]
    return f"""# Release bundle

Two models for the Aurelia Skyways Companion Animal Travel Desk language model (seed {report['seed']}):

| directory | what it is |
|---|---|
| `pretrained/` | pretrained from scratch on the synthetic corpus (final epoch) |
| `sft/` | the pretrained model after supervised fine-tuning on question-answer pairs (best epoch by SFT-validation loss) |

Each directory holds `model.pt` (weights only), `tokenizer.json`, `model_config.json` and
`bundle_manifest.json` (sha256 of the other files, git commit, torch version, parameter count).

Which seed: {sel['rule']} (validation loss by seed: {sel['val_loss_by_seed']}). Test results were
not used.

Run (from the repository root, with `requirements.txt` installed):

    python scripts/generate.py --bundle bundle/sft --prompt "Who manages the pet lounge at Caldreth?"
    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Caldreth opens at"
    python scripts/generate.py --bundle bundle/sft --interactive
"""