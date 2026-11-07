# ruff: noqa: E501
"""Generate text from a release bundle (the course demo).

    python scripts/generate.py --bundle bundle/sft --prompt "Who manages the pet lounge at Caldreth?"
    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Caldreth opens at"
    python scripts/generate.py --bundle bundle/sft --interactive

Loads ONLY from the bundle directory (model.pt, tokenizer.json, model_config.json, checked against
bundle_manifest.json) and prints which model it loaded ("pretrained" or "sft"). Defaults: CPU,
greedy (temperature 0). An SFT bundle wraps the prompt as "Question: <prompt>\nAnswer:" and stops at
a newline; a pretrained bundle continues the raw text. Override with --format raw|qa.
Interactive commands: ":quit", ":set max_new_tokens|temperature|top_k|seed|format <value>".

    python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who manages the pet lounge at Caldreth?"
    python scripts/generate.py --bundle-root bundle --compare --qa "Who manages the pet lounge at Caldreth?"

``--qa Q`` formats Q as "Question: Q
Answer:" for ANY bundle (also the pretrained one) and decodes to <|eos|> or the newline.
``--compare`` runs the same question through every model in ``--bundle-root`` (pretrained, sft_early_stopped = the pre-specified
primary SFT, sft_fixed3 = the post-hoc fixed 3-epoch SFT) and prints all of them; it needs --qa (or --prompt, read as a question).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from slm.bundle import BundleError, load_bundle  # noqa: E402
from slm.generation import generate_text, newline_token_ids  # noqa: E402


class Settings:
    def __init__(self, a: argparse.Namespace, kind: str) -> None:
        self.max_new_tokens = a.max_new_tokens
        self.temperature = a.temperature
        self.top_k = a.top_k
        self.seed = a.seed
        self.format = a.format or ("qa" if kind == "sft" else "raw")

    def describe(self) -> str:
        return (f"max_new_tokens={self.max_new_tokens} temperature={self.temperature} "
                f"top_k={self.top_k} seed={self.seed} format={self.format}")

    def set(self, key: str, value: str) -> None:
        if key in ("max_new_tokens", "seed"):
            setattr(self, key, int(value))
        elif key == "temperature":
            self.temperature = float(value)
        elif key == "top_k":
            self.top_k = None if value.lower() in ("none", "0") else int(value)
        elif key == "format" and value in ("raw", "qa"):
            self.format = value
        else:
            raise ValueError(f"cannot set {key!r} to {value!r}")


def complete(b, s: Settings, prompt: str, device) -> str:
    qa = s.format == "qa"
    text = f"Question: {prompt}\nAnswer:" if qa else prompt
    stop = newline_token_ids(b.tokenizer) if qa else ()
    out, gen = generate_text(b.model, b.tokenizer, text, s.max_new_tokens, stop, device,
                             s.temperature, s.top_k, s.seed)
    if gen.truncated_prompt:
        print(f"warning: prompt was cut by {gen.n_dropped} tokens from the left to fit the context",
              file=sys.stderr)
    return out.split("\n", 1)[0].strip() if qa else out


def read_lines():
    if not sys.stdin.isatty():  # piped input (tests, scripts)
        yield from sys.stdin
        return
    while True:
        try:
            yield input(">>> ")
        except EOFError:
            return


def label(b) -> str:
    """kind plus the SFT variant when the manifest names one (early_stopped_primary / fixed3_posthoc)."""
    v = b.manifest.get("variant")
    return f"{b.kind} [{v}]" if v else b.kind


def compare(a: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    """The same question through every bundle under --bundle-root (pretrained first)."""
    question = a.qa if a.qa is not None else a.prompt
    if question is None:
        ap.error("--compare needs --qa (or --prompt)")
    root = Path(a.bundle_root)
    names = [n for n in ("pretrained", "sft_early_stopped", "sft_fixed3", "sft") if (root / n).is_dir()]
    if not names or "pretrained" not in names:
        print(f"error: {root} holds no 'pretrained' bundle (found {names})", file=sys.stderr)
        return 2
    if a.device == "cuda" and not torch.cuda.is_available():
        print("error: --device cuda requested but CUDA is not available; use --device cpu", file=sys.stderr)
        return 2
    print(f"question: {question}")
    for n in names:
        try:
            b = load_bundle(root / n, a.device)
        except BundleError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        s = Settings(a, b.kind)
        s.format = "qa"
        print(f"[{n}: {label(b)}] {complete(b, s, question, a.device)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # A model can emit bytes that are not valid text; never let a legacy console code page (cp1252)
    # turn that into a crash during a demo.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bundle", help="a bundle directory, e.g. bundle/sft_early_stopped (not needed with --compare)")
    ap.add_argument("--bundle-root", default="bundle", help="directory holding the bundles, for --compare")
    ap.add_argument("--prompt", help="text to complete (omit with --interactive)")
    ap.add_argument("--qa", help="a question: formatted as 'Question: <q>\nAnswer:' for any bundle")
    ap.add_argument("--compare", action="store_true", help="run the question through every bundle in --bundle-root and print all answers")
    ap.add_argument("--interactive", action="store_true", help="REPL; the model stays loaded")
    ap.add_argument("--max-new-tokens", type=int, default=48)
    ap.add_argument("--temperature", type=float, default=0.0, help="0 = greedy")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0, help="sampling seed (temperature > 0)")
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    ap.add_argument("--format", choices=["raw", "qa"], default=None)
    a = ap.parse_args(argv)
    if a.compare:
        return compare(a, ap)
    if a.bundle is None:
        ap.error("give --bundle (or --compare)")
    if not a.interactive and a.prompt is None and a.qa is None:
        ap.error("give --prompt, --qa or --interactive")
    if a.qa is not None and a.prompt is not None:
        ap.error("give --prompt or --qa, not both")
    if a.device == "cuda" and not torch.cuda.is_available():
        print("error: --device cuda requested but CUDA is not available; use --device cpu",
              file=sys.stderr)
        return 2
    try:
        b = load_bundle(a.bundle, a.device)
    except BundleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    s = Settings(a, b.kind)
    if a.qa is not None:
        s.format = "qa"
    print(f"loaded: {label(b)} (seed {b.manifest['seed']}, {b.manifest['n_params']:,} params) "
          f"from {b.path} on {a.device}")
    if not a.interactive:
        text = a.qa if a.qa is not None else a.prompt
        print(f"settings: {s.describe()}")
        print(f"{'question' if a.qa is not None else 'prompt'}: {text}")
        print(f"completion: {complete(b, s, text, a.device)}")
        return 0
    print('type a prompt; ":set key value" changes a setting, ":quit" leaves')
    for line in read_lines():
        line = line.strip()
        try:
            if not line:
                continue
            if line in (":quit", ":q"):
                break
            if line.startswith(":set "):
                _, key, value = line.split(maxsplit=2)
                s.set(key, value)
                print(f"settings: {s.describe()}")
                continue
            comp = complete(b, s, line, a.device)
        except (ValueError, EOFError) as e:
            print(f"error: {e}")
            continue
        print(f"[{b.kind} | {s.describe()}]")
        print(f"completion: {comp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())