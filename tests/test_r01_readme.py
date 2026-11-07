# ruff: noqa: E501
"""R01 5 / R09: the root README only names files that exist, and its generate.py / make_bundle.py commands run (mock release bundle, CPU)."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from slm.bundle.release import Entry, build_release
from slm.model import ModelConfig, Transformer, save_checkpoint
from slm.split_manifest import build_manifest
from slm.tokenizer import train_tokenizer

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
COMMANDS = [m.group(1).rstrip() for m in re.finditer(r"^ {4}(python [^\n#]+?)\s*(?:#.*)?$", README, flags=re.M)]


def test_readme_has_the_sections_the_course_asks_for():
    for title in ("## 1. Run the trained models", "### Hardware and speed", "### Required files", "## 2. Reproduce the tables", "## 3. Reproduce the training",
                  "## 4. Repository map", "## 5. Statements"):
        assert title in README
    for phrase in ("pip install -r bundle/requirements.txt", "CPU", "no training", "CUDA", "Example output", "pre-specified primary", "post-hoc secondary"):
        assert phrase in README


def test_every_script_in_a_code_block_exists_and_every_mentioned_repo_path_exists():
    assert len(COMMANDS) >= 10
    for cmd in COMMANDS:
        script = shlex.split(cmd)[1]
        if script.startswith("-"):  # python -m venv / pytest
            continue
        assert (ROOT / script).is_file(), f"{cmd!r}: {script} does not exist"
    for path in set(re.findall(r"`((?:scripts|configs|docs|src/slm|tests)/[\w/.\-]*)`", README)):
        assert (ROOT / path.rstrip("/")).exists(), f"README mentions {path} which does not exist"


@pytest.fixture(scope="module")
def mock_bundle(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("readme_bundle")
    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        (tmp / n).write_bytes((ROOT / "tests" / "fixtures" / n).read_bytes())
    man = build_manifest({tmp / "mock_corpus_train.txt": "train", tmp / "mock_corpus_val.txt": "val"}, tmp / "splits.json")
    tok = train_tokenizer(man, vocab_size=4096, min_frequency=1)
    tok.save(tmp / "tokenizer.json")
    cfg = ModelConfig(vocab_size=tok.vocab_size, context_len=96, n_layer=1, n_head=2, d_model=16, d_ff=32, dropout=0.0)
    entries = []
    for i, (name, kind, variant) in enumerate([("pretrained", "pretrained", None), ("sft_early_stopped", "sft", "early_stopped_primary"), ("sft_fixed3", "sft", "fixed3_posthoc")]):
        torch.manual_seed(i)
        p = tmp / f"{name}.pt"
        save_checkpoint(Transformer(cfg), p, {"epoch": 1})
        entries.append(Entry(name, kind, p, variant, f"mock {name}"))
    build_release(tmp / "bundle", tmp / "tokenizer.json", entries, [])
    return tmp / "bundle"


def run(args, stdin=None):
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1"}  # CPU only
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, input=stdin, env=env, timeout=300)


def to_mock(cmd: str, mock_bundle: Path) -> list[str]:
    out = []
    for a in shlex.split(cmd)[1:]:
        if a == "bundle":
            out.append(str(mock_bundle))
        elif a.startswith("bundle/"):
            out.append(str(mock_bundle / a.split("/", 1)[1]))
        else:
            out.append(a)
    return out


def test_every_generate_command_in_the_readme_runs_on_the_mock_bundle(mock_bundle):
    gen = [c for c in COMMANDS if c.split()[1] == "scripts/generate.py"]
    assert len(gen) >= 5 and any("--interactive" in c for c in gen) and any("--compare" in c for c in gen) and any("--qa" in c for c in gen)
    assert {"bundle/sft_early_stopped", "bundle/sft_fixed3", "bundle/pretrained"} <= {t for c in gen for t in shlex.split(c) if t.startswith("bundle/")}
    for cmd in gen:
        args = to_mock(cmd, mock_bundle)
        r = run(args, stdin=":quit\n" if "--interactive" in args else None)
        assert r.returncode == 0, f"{cmd}\n{r.stderr}"
        if "--compare" in args:
            assert r.stdout.count("completion") == 0 and r.stdout.count("[") >= 3, cmd
        else:
            assert r.stdout.splitlines()[0].startswith("loaded: "), cmd
            if "--prompt" in args or "--qa" in args:
                assert any(line.startswith("completion: ") for line in r.stdout.splitlines()), cmd


def test_the_verify_command_in_the_readme_runs_on_the_mock_bundle(mock_bundle):
    ver = [c for c in COMMANDS if c.split()[1] == "scripts/make_bundle.py" and "--verify" in c]
    assert ver
    r = run(to_mock(ver[0], mock_bundle))
    assert r.returncode == 0 and "MANIFEST OK" in r.stdout


def test_help_and_list_variants_in_the_readme_run():
    ran = 0
    for cmd in COMMANDS:
        args = shlex.split(cmd)[1:]
        if args[-1] == "--help" or args[1:] == ["--list"]:
            r = run(args)
            assert r.returncode == 0, f"{cmd}\n{r.stderr[-500:]}"
            ran += 1
    assert ran >= 1
