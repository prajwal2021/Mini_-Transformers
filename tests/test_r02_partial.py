# ruff: noqa: E501
"""R02: partial-corpus helpers: the manifest never lists or opens test; the overlap check reads v1 manifests."""

import importlib.util
import json
from pathlib import Path

import yaml

from slm.eval.probes import build_probes, load_facts
from slm.split_manifest import SplitManifest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def corpus(tmp_path, with_test=False):
    d = tmp_path / "corpus"
    d.mkdir()
    for s in ("train", "val"):
        (d / f"{s}.jsonl").write_text(json.dumps({"text": f"{s} document about pets"}) + "\n", encoding="utf-8")
    if with_test:
        (d / "test.jsonl").write_text("not json at all", encoding="utf-8")  # opening it as json would raise
    return d


def test_partial_manifest_lists_train_and_val_only_and_works_without_a_test_file(tmp_path):
    d = corpus(tmp_path)
    assert not (d / "test.jsonl").exists()
    load("partial_manifest").main(["--corpus", str(d), "--out", str(tmp_path / "out")])
    man = SplitManifest.load(tmp_path / "out" / "splits.json")
    assert {e.split for e in man.files("train") + man.files("val")} == {"train", "val"}
    assert man.files("test") == []


def test_partial_manifest_does_not_touch_an_existing_test_file(tmp_path):
    d = corpus(tmp_path, with_test=True)
    before = (d / "test.jsonl").stat().st_atime_ns, (d / "test.jsonl").read_bytes()
    load("partial_manifest").main(["--corpus", str(d), "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out" / "test.jsonl").exists()
    assert "test" not in (tmp_path / "out" / "splits.json").read_text()
    assert (d / "test.jsonl").read_bytes() == before[1]


def test_overlap_check_accepts_a_v1_manifest_and_prints_the_shared_8gram(tmp_path, capsys):
    novel = next(i for i in build_probes(load_facts(ROOT / "data/kb/kb.json")).items if i.probe_frame == "novel")
    d = tmp_path / "c"
    d.mkdir()
    (d / "train.jsonl").write_text(json.dumps({"text": f"intro {novel.prompt} {novel.value} outro"}) + "\n", encoding="utf-8")
    (d / "val.jsonl").write_text(json.dumps({"text": "val only"}) + "\n", encoding="utf-8")
    load("partial_manifest").main(["--corpus", str(d), "--out", str(tmp_path / "m")])
    rc = load("check_probe_overlap").main(["--split-manifest", str(tmp_path / "m" / "splits.json")])
    out = capsys.readouterr().out
    assert rc == 1 and "8-gram:" in out and "FAIL" in out


def test_partial_config_never_targets_the_real_run_dir_or_the_real_ledger():
    cfg = yaml.safe_load((ROOT / "configs" / "partial_dryrun.yaml").read_text())
    assert cfg["out_dir"] == "runs/partial_dryrun" and cfg["ledger"].startswith("runs/partial_dryrun/")
    assert cfg["sweep"]["epochs"] == 3 and len(cfg["sweep"]["grid"]["lr"]) * len(cfg["sweep"]["grid"]["dropout"]) == 2
    assert "runs/partial_dryrun/" in (ROOT / ".gitignore").read_text()
