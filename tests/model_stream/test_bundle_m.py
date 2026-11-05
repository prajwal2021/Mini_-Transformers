# ruff: noqa: E501
"""Release bundle, generate.py CLI, make_bundle.py and the fresh-clone test."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from slm.bundle import BundleError, build_bundle, load_bundle, select_seed, sha256_file
from slm.model import ModelConfig, Transformer, save_checkpoint

ROOT = Path(__file__).resolve().parents[2]
GENERATE = ROOT / "scripts" / "generate.py"
VAL = {0: 3.2, 1: 2.9, 2: 3.0}


def make_runs(tmp, tok, val=None, sft_seeds=(0, 1, 2)):
    cfg = ModelConfig(vocab_size=tok.vocab_size, context_len=96, n_layer=1, n_head=2, d_model=16,
                      d_ff=32, dropout=0.0)
    pre, sft = tmp / "pre", tmp / "sft"
    for k, v in (val or VAL).items():
        c = pre / f"seed{k}" / "checkpoints"
        c.mkdir(parents=True)
        for ep in (1, 2):
            torch.manual_seed(10 * k + ep)
            save_checkpoint(Transformer(cfg), c / f"epoch_{ep:03d}.pt",
                            {"epoch": ep, "train_config": {"lr": 1}})
        torch.save({"optimizer": {"junk": 1}}, c / "last.pt")
        (pre / f"seed{k}" / "summary.json").write_text(json.dumps({"final_val_loss": v}))
        if k in sft_seeds:
            c = sft / f"seed{k}" / "checkpoints"
            c.mkdir(parents=True)
            torch.manual_seed(100 + k)
            save_checkpoint(Transformer(cfg), c / "best.pt", {"val_loss": 1.0})
    tok.save(tmp / "tokenizer.json")
    return pre, sft, tmp / "tokenizer.json"


@pytest.fixture()
def runs(tmp_path, tokenizer):
    return make_runs(tmp_path, tokenizer)


@pytest.fixture()
def bundle(tmp_path, runs):
    pre, sft, tok = runs
    return build_bundle(pre, sft, tok, tmp_path / "bundle") | {"root": tmp_path / "bundle"}


# ---- seed rule -------------------------------------------------------------------------------
def test_seed_rule_is_lowest_validation_loss(runs):
    pre, sft, _ = runs
    c = select_seed(pre, sft)
    assert c["seed"] == 1 and c["val_loss_by_seed"] == VAL and "validation" in c["rule"]
    assert select_seed(pre, sft, seed=2)["rule"] == "explicit --seed"
    with pytest.raises(BundleError, match="not available"):
        select_seed(pre, sft, seed=7)


def test_seed_rule_needs_an_sft_run_and_breaks_ties_low(tmp_path, tokenizer):
    pre, sft, _ = make_runs(tmp_path, tokenizer, {0: 3.0, 1: 2.0, 2: 2.0}, sft_seeds=(0, 2))
    assert select_seed(pre, sft)["seed"] == 2  # seed 1 has no SFT run
    pre2, sft2, _ = make_runs(tmp_path / "b", tokenizer, {0: 2.0, 1: 2.0})
    assert select_seed(pre2, sft2)["seed"] == 0
    with pytest.raises(BundleError, match="no seed has both"):
        select_seed(tmp_path / "nope", tmp_path / "nope")


# ---- contents --------------------------------------------------------------------------------
def test_bundle_contents_and_manifest(bundle):
    root = bundle["root"]
    assert bundle["seed"] == 1 and set(bundle["bundles"]) == {"pretrained", "sft"}
    assert (root / "README_BUNDLE.md").exists()
    req = (root / "requirements.txt").read_text()
    assert "torch==" in req and "regex==" in req and "PyYAML==" in req and "whl/cpu" in req
    for kind in ("pretrained", "sft"):
        d = root / kind
        assert sorted(p.name for p in d.iterdir()) == [
            "bundle_manifest.json", "model.pt", "model_config.json", "tokenizer.json"]
        m = json.loads((d / "bundle_manifest.json").read_text())
        assert m["kind"] == kind and m["seed"] == 1 and m["n_params"] > 0
        assert m["git"]["commit"] and m["torch"] == torch.__version__
        assert set(m["files"]) == {"model.pt", "tokenizer.json", "model_config.json"}
        for name, h in m["files"].items():
            assert sha256_file(d / name) == h
        blob = torch.load(d / "model.pt", map_location="cpu", weights_only=True)
        assert set(blob) == {"config", "state_dict"}  # weights only: no optimizer, no train state
    assert bundle["total_bytes"] > 0


def test_bundle_weights_come_from_the_selected_seed(bundle, runs):
    pre, sft, _ = runs
    want = {"pretrained": pre / "seed1" / "checkpoints" / "epoch_002.pt",
            "sft": sft / "seed1" / "checkpoints" / "best.pt"}
    for kind, src in want.items():
        a = torch.load(src, map_location="cpu", weights_only=True)["state_dict"]
        b = load_bundle(bundle["root"] / kind).model.state_dict()
        assert all(torch.equal(a[k], b[k]) for k in a)
        m = json.loads((bundle["root"] / kind / "bundle_manifest.json").read_text())
        assert m["source_checkpoint"] == src.name and m["source_sha256"] == sha256_file(src)


def test_load_bundle_errors_are_clear(bundle, tmp_path):
    root = bundle["root"]
    with pytest.raises(BundleError, match="directory not found"):
        load_bundle(tmp_path / "nowhere")
    with pytest.raises(BundleError, match=r"contains bundles \['pretrained', 'sft'\]"):
        load_bundle(root)
    (root / "sft" / "tokenizer.json").rename(root / "sft" / "tok.bak")
    with pytest.raises(BundleError, match="required file missing.*tokenizer.json"):
        load_bundle(root / "sft")
    (root / "sft" / "tok.bak").rename(root / "sft" / "tokenizer.json")
    with open(root / "pretrained" / "model.pt", "ab") as f:
        f.write(b"x")
    with pytest.raises(BundleError, match="does not match its sha256"):
        load_bundle(root / "pretrained")
    m = root / "sft" / "bundle_manifest.json"
    m.write_text(m.read_text().replace('"kind": "sft"', '"kind": "other"'))
    with pytest.raises(BundleError, match="unsupported"):
        load_bundle(root / "sft")


# ---- generate.py -------------------------------------------------------------------------------
def gen(*args, stdin=None):
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}  # CUDA hidden: CPU only
    return subprocess.run([sys.executable, str(GENERATE), *args], capture_output=True, text=True,
                          input=stdin, env=env, timeout=300)


def test_generate_on_cpu_loads_each_kind_and_is_deterministic(bundle):
    outs = {}
    for kind in ("pretrained", "sft"):
        args = ["--bundle", str(bundle["root"] / kind), "--prompt", "Who looks after the pets?",
                "--max-new-tokens", "6", "--device", "cpu"]
        a, b = gen(*args), gen(*args)
        assert a.returncode == 0, a.stderr
        lines = a.stdout.splitlines()
        assert lines[0].startswith(f"loaded: {kind} (seed 1,") and "on cpu" in lines[0]
        assert lines[1] == (f"settings: max_new_tokens=6 temperature=0.0 top_k=None seed=0 "
                            f"format={'qa' if kind == 'sft' else 'raw'}")
        assert lines[2] == "prompt: Who looks after the pets?"
        assert a.stdout == b.stdout and lines[3].startswith("completion: ")
        outs[kind] = lines[3]
    assert outs["pretrained"] != "completion: " and outs["sft"] != "completion: "


def test_generate_sampling_options_are_seeded(bundle):
    base = ["--bundle", str(bundle["root"] / "pretrained"), "--prompt", "Hello there",
            "--max-new-tokens", "8", "--temperature", "1.5", "--top-k", "20"]
    a, b = gen(*base, "--seed", "4"), gen(*base, "--seed", "4")
    c = gen(*base, "--seed", "5")
    assert a.stdout == b.stdout and "temperature=1.5 top_k=20 seed=4" in a.stdout
    assert c.returncode == 0 and c.stdout.splitlines()[-1] != a.stdout.splitlines()[-1]


def test_generate_interactive_keeps_the_model_loaded(bundle):
    r = gen("--bundle", str(bundle["root"] / "sft"), "--interactive", "--max-new-tokens", "4",
            stdin="first question\n:set temperature 0.7\n:set bogus 1\nsecond question\n:quit\nnever\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("loaded: sft") == 1  # loaded once
    assert r.stdout.count("completion: ") == 2 and "never" not in r.stdout
    assert "[sft | max_new_tokens=4 temperature=0.0" in r.stdout
    assert "[sft | max_new_tokens=4 temperature=0.7" in r.stdout
    assert "error: cannot set 'bogus'" in r.stdout


def test_generate_error_messages(bundle, tmp_path):
    r = gen("--bundle", str(tmp_path / "missing"), "--prompt", "x")
    assert r.returncode == 2 and r.stderr.startswith("error: bundle directory not found")
    r = gen("--bundle", str(bundle["root"]), "--prompt", "x")
    assert r.returncode == 2 and "pass one of them" in r.stderr
    (bundle["root"] / "sft" / "model.pt").unlink()
    r = gen("--bundle", str(bundle["root"] / "sft"), "--prompt", "x")
    assert r.returncode == 2 and "required file missing" in r.stderr and "model.pt" in r.stderr
    r = gen("--bundle", str(bundle["root"] / "pretrained"))
    assert r.returncode == 2 and "--prompt" in r.stderr


def test_generate_uses_only_the_bundle(bundle, tmp_path):
    """No run directory, config or data path is needed: copy the bundle alone and run it."""
    import shutil

    shutil.copytree(bundle["root"] / "sft", tmp_path / "elsewhere" / "sft")
    r = gen("--bundle", str(tmp_path / "elsewhere" / "sft"), "--prompt", "Hi", "--max-new-tokens", "3")
    assert r.returncode == 0 and r.stdout.startswith("loaded: sft")


def test_make_bundle_cli(tmp_path, runs):
    pre, sft, tok = runs
    out = tmp_path / "cli_bundle"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_bundle.py"), "--pretrain-run",
                        str(pre), "--sft-run", str(sft), "--tokenizer", str(tok), "--out", str(out)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "total bundle size:" in r.stdout and (out / "sft" / "model.pt").exists()
    bad = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_bundle.py"), "--pretrain-run",
                          str(tmp_path / "x"), "--sft-run", str(tmp_path / "y"), "--tokenizer",
                          str(tok)], capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and bad.stderr.startswith("error:")


@pytest.mark.slow
def test_fresh_clone_script_runs_both_bundles(bundle):
    """Copy of the repo source + the bundle in a temp dir, no install (network not needed)."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fresh_clone_test.py"), "--bundle",
                        str(bundle["root"]), "--source", "worktree", "--no-install"],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads(r.stdout)
    assert rep["ok"] and set(rep["runs"]) == {"pretrained", "sft"}
    for run in rep["runs"].values():
        assert run["deterministic"] and run["completion"] and not run["prompt_in_mock_corpus"]