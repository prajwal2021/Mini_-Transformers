# ruff: noqa: E501
"""R01 5: docs/README.md only names files that exist, and its generate.py commands run (mock bundle, CPU)."""

import importlib.util
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from slm.bundle import build_bundle
from slm.model import ModelConfig, Transformer, save_checkpoint
from slm.split_manifest import build_manifest
from slm.tokenizer import train_tokenizer

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
COMMANDS = [m.group(1).rstrip() for m in re.finditer(r"^ {4}(python [^\n#]+?)\s*(?:#.*)?$", README, flags=re.M)]


def test_readme_has_the_sections_the_course_asks_for():
    for title in ("## 1. Installation", "## 2. Hardware", "## 3. Required files", "## 4. Inference", "## 5. Example inputs",
                  "## 6. Reproducing the training", "## 7. What is in this repo"):
        assert title in README
    assert "without retraining" in README and "CUDA GPU with about 5 GB" in README and "CPU is enough" in README


def test_every_script_in_a_code_block_exists_and_every_mentioned_repo_path_exists():
    assert len(COMMANDS) >= 10
    for cmd in COMMANDS:
        script = shlex.split(cmd)[1]
        if script.startswith("-"):  # python -m venv / pytest
            continue
        assert (ROOT / script).is_file(), f"{cmd!r}: {script} does not exist"
    for path in set(re.findall(r"`((?:scripts|configs|docs|src/slm|tests)/[\w/.\-]*)`", README)):
        assert (ROOT / path.rstrip("/")).exists(), f"README mentions {path} which does not exist"


def test_the_stage_list_in_the_readme_is_the_orchestrators():
    spec = importlib.util.spec_from_file_location("run_real", ROOT / "scripts" / "run_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    listed = re.search(r"Stages in order: (.+?)\. A dry run", README, flags=re.S).group(1)
    assert re.findall(r"`(\w+)`", listed) == mod.STAGES


@pytest.fixture(scope="module")
def mock_bundle(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("readme_bundle")
    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        (tmp / n).write_bytes((ROOT / "tests" / "fixtures" / n).read_bytes())
    man = build_manifest({tmp / "mock_corpus_train.txt": "train", tmp / "mock_corpus_val.txt": "val"}, tmp / "splits.json")
    tok = train_tokenizer(man, vocab_size=4096, min_frequency=1)
    tok.save(tmp / "tokenizer.json")
    cfg = ModelConfig(vocab_size=tok.vocab_size, context_len=96, n_layer=1, n_head=2, d_model=16, d_ff=32, dropout=0.0)
    pre, sft = tmp / "pre", tmp / "sft"
    c = pre / "seed0" / "checkpoints"
    c.mkdir(parents=True)
    torch.manual_seed(1)
    save_checkpoint(Transformer(cfg), c / "epoch_001.pt", {"epoch": 1, "train_config": {"lr": 1}})
    (pre / "seed0" / "summary.json").write_text('{"final_val_loss": 3.0}')
    s = sft / "seed0" / "checkpoints"
    s.mkdir(parents=True)
    save_checkpoint(Transformer(cfg), s / "best.pt", {"val_loss": 1.0})
    build_bundle(pre, sft, tmp / "tokenizer.json", tmp / "bundle")
    return tmp / "bundle"


def run(args, stdin=None):
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}  # CPU only
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, input=stdin, env=env, timeout=300)


def test_every_generate_command_in_the_readme_runs_on_the_mock_bundle(mock_bundle):
    gen = [c for c in COMMANDS if c.split()[1] == "scripts/generate.py"]
    assert len(gen) >= 4 and any("--interactive" in c for c in gen) and any("--temperature" in c for c in gen)
    assert {"bundle/sft", "bundle/pretrained"} <= {t for c in gen for t in shlex.split(c) if t.startswith("bundle/")}
    for cmd in gen:
        args = [a.replace("bundle/", str(mock_bundle) + os.sep, 1) if a.startswith("bundle/") else a for a in shlex.split(cmd)[1:]]
        r = run(args, stdin=":quit\n" if "--interactive" in args else None)
        assert r.returncode == 0, f"{cmd}\n{r.stderr}"
        assert r.stdout.splitlines()[0].startswith("loaded: "), cmd
        if "--prompt" in args:
            assert any(line.startswith("completion: ") for line in r.stdout.splitlines()), cmd


def test_help_and_list_variants_in_the_readme_run():
    ran = 0
    for cmd in COMMANDS:
        args = shlex.split(cmd)[1:]
        if args[-1] == "--help" or args[1:] == ["--list"]:
            r = run(args)
            assert r.returncode == 0, f"{cmd}\n{r.stderr[-500:]}"
            ran += 1
    assert ran >= 2
