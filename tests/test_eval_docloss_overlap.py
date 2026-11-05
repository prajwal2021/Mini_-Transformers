"""E02: document-level loss by regime, probe overlap CLI, wording audit."""

import importlib.util
import json
from pathlib import Path

import pytest

from slm.eval.docloss import attach_texts, doc_loss_by_regime
from slm.eval.wording import NOVEL, audit_markdown

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def doc(i, split, regime, role="route planner", tone="calm", text="a b c d"):
    return {
        "doc_id": f"{split}-{i}", "split": split, "style_regime": regime,
        "style_card": {"author_role": role, "tone": tone}, "text": text,
    }


def fake_nll(text):
    words = text.split()
    return 2.0 * len(words) + words.count("hard"), len(words)  # 2 nats/token, +1 per "hard"


def test_doc_loss_by_regime_is_token_weighted() -> None:
    docs = [
        doc(1, "val", "iid", text="a b c d"),  # 8 nll, 4 tokens
        doc(2, "val", "iid", text="a b"),  # 4 nll, 2 tokens
        doc(3, "val", "novel", role="route editor", text="hard hard"),  # 6 nll, 2 tokens
        doc(4, "test", "novel", tone="apologetic", text="a hard"),  # 5 nll, 2 tokens
        doc(5, "train", "train", text="ignored"),
    ]
    df = doc_loss_by_regime(fake_nll, docs)
    assert set(df["split"]) == {"val", "test"}
    get = lambda s, r, g, v: df[(df.split == s) & (df.regime == r) & (df.group_by == g)  # noqa: E731
                                & (df.group == v)].iloc[0]
    a = get("val", "iid", "all", "all")
    assert (a.n_docs, a.n_tokens) == (2, 6) and a.mean_nll == pytest.approx(12 / 6)
    assert get("val", "novel", "all", "all").mean_nll == pytest.approx(3.0)
    assert get("val", "novel", "author_role", "route editor").n_docs == 1
    assert get("val", "iid", "held_out_style", "no").n_docs == 2
    assert get("val", "novel", "held_out_style", "yes").n_docs == 1
    assert get("test", "novel", "held_out_style", "yes").mean_nll == pytest.approx(2.5)
    assert get("test", "novel", "tone", "apologetic").n_tokens == 2


def test_attach_texts_joins_on_doc_id() -> None:
    rows = [{"doc_id": "x"}, {"doc_id": "y"}]
    assert attach_texts(rows, {"x": "hello"}) == [{"doc_id": "x", "text": "hello"}]


def test_wording_audit_has_a_row_per_attribute() -> None:
    md = audit_markdown()
    assert md.count("\n| ") >= 21 and all(attr in md for attr in NOVEL)


def test_overlap_cli_passes_and_fails(tmp_path, capsys) -> None:
    cli = _load_script("check_probe_overlap")
    clean = tmp_path / "clean.jsonl"
    clean.write_text(json.dumps({"text": "Nothing about pets appears in this short text."}) + "\n",
                     encoding="utf-8")
    manifest = tmp_path / "split_manifest.json"
    manifest.write_text(json.dumps({"splits": {"train": {"files": ["clean.jsonl"]}}}),
                        encoding="utf-8")
    assert cli.main(["--split-manifest", str(manifest)]) == 0

    leak = tmp_path / "leak.txt"
    leak.write_text(
        "Early arrivals at Caldreth wait until the pet lounge begins service at 07:53 sharp.",
        encoding="utf-8",
    )
    manifest.write_text(json.dumps({"train": ["leak.txt"]}), encoding="utf-8")
    assert cli.main(["--split-manifest", str(manifest)]) == 1
    assert "FAIL" in capsys.readouterr().out
