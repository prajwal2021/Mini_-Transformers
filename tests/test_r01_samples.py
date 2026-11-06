# ruff: noqa: E501
"""R01 4: the checkpoint sample generator (prompt lists, flags, selection, a tiny end-to-end run)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from slm.integration import samples as S
from slm.sft_eval import Taxonomy

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
FACTS = {f["fact_id"]: f for f in KB["measured_facts"]}
TAX = Taxonomy.from_kb(KB)


def test_prompt_lists_are_fixed_and_cover_the_required_mix():
    p10, p20 = S.build_prompts(KB, 10), S.build_prompts(KB, 20)
    assert [p["prompt_kind"] for p in p10].count("canonical") == 5 and [p["prompt_kind"] for p in p10].count("novel") == 3
    assert [p["prompt_kind"] for p in p10].count("off_domain") == 2 and len(p20) == 20
    assert p20[:10] == p10 and p10 == S.build_prompts(KB, 10)  # deterministic, 20 extends 10
    cells = {f"{p['freq_bin']}_{p['div_bin']}" for p in p10 if p["prompt_kind"] == "canonical"}
    assert len(cells) == 5  # five different freq x div cells
    for p in p20:
        assert p["prompt"] == p["prompt"].strip() and p["prompt"][0].isupper()
        if p["fact_id"]:
            assert FACTS[p["fact_id"]]["value"].lower() not in p["prompt"].lower()
    canon = next(p for p in p10 if p["prompt_kind"] == "canonical")
    assert canon["prompt"] == FACTS[canon["fact_id"]]["canonical_prefix"].rstrip()


def test_completion_is_cut_at_the_first_sentence_end():
    assert S.completion_of(" Elara Voss. The next sentence") == "Elara Voss."
    assert S.completion_of(" $85.\nMore") == "$85."
    assert S.completion_of("") == ""


def prompt_for(kind="canonical"):
    return next(p for p in S.build_prompts(KB, 20) if p["prompt_kind"] == kind)


def test_flags_follow_the_taxonomy():
    p = prompt_for()
    f = FACTS[p["fact_id"]]
    other = next(v for v in TAX.values_of[f["attribute_id"]] if v != f["value"])
    assert S.flag_of(TAX, FACTS, p, f" {f['value']}.") == "value_correct"
    assert S.flag_of(TAX, FACTS, p, f" {other}.") == "wrong_value"
    assert S.flag_of(TAX, FACTS, p, " 999999 zebras.") in ("hallucinated", "gibberish")
    assert S.flag_of(TAX, FACTS, p, "") == "gibberish"
    off = prompt_for("off_domain")
    assert S.flag_of(TAX, FACTS, off, " Paris.") == "off_domain_ok"
    assert S.flag_of(TAX, FACTS, off, " the the the the the the") == "gibberish"


def synthetic(n_ck=4) -> pd.DataFrame:
    rows = []
    for ci in range(n_ck):
        for i, flag in enumerate(["value_correct", "wrong_value", "gibberish", "hallucinated", "value_correct"]):
            rows.append({"data_status": "MOCK", "section": "checkpoint_series", "checkpoint": str(10 * (ci + 1)), "epoch": ci + 1, "seed": 0,
                         "prompt_id": f"c{i}", "prompt_kind": "canonical", "fact_id": "F001", "freq_bin": "high", "div_bin": "templated",
                         "setting": "greedy", "sample_idx": 0, "prompt": "p", "completion": f"c{ci}{i}", "flag": flag})
    return pd.DataFrame(rows, columns=S.COLUMNS)


def test_selection_spreads_over_checkpoints_and_is_deterministic():
    df = synthetic()
    sel = S.select_samples(df, 6)
    assert (sel["selected_as"] == "success").sum() == 6 and (sel["selected_as"] == "failure").sum() == 6
    succ = sel[sel["selected_as"] == "success"]
    assert succ["checkpoint"].nunique() == 4  # all four checkpoints appear
    assert sel.equals(S.select_samples(df, 6))
    assert not sel[sel["selected_as"] == "failure"]["flag"].isin(["value_correct"]).any()


def test_selection_is_not_padded_when_successes_are_missing():
    df = synthetic()
    df["flag"] = df["flag"].replace("value_correct", "wrong_value")
    sel = S.select_samples(df, 6)
    assert (sel["selected_as"] == "success").sum() == 0 and (sel["selected_as"] == "failure").sum() == 6
    md = S.to_markdown(df, sel, 6, "MOCK")
    assert "Only 0 of 6 successes" in md and "NOTHING HERE IS A RESULT" in md


def test_report_categories_cover_both_sides():
    cats = {c["category"] for c in S.categories(S.select_samples(synthetic(), 6))}
    assert "success: recalled fact" in cats and any(c.startswith("failure:") for c in cats)


@pytest.mark.slow
def test_script_runs_on_a_tiny_trained_model(tmp_path):
    import importlib.util
    import shutil

    from slm.model import ModelConfig
    from slm.split_manifest import build_manifest
    from slm.tokenizer import train_tokenizer
    from slm.train import TrainConfig
    from slm.train.runner import run_seeds

    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        shutil.copy(ROOT / "tests" / "fixtures" / n, tmp_path / n)
    man = build_manifest({tmp_path / "mock_corpus_train.txt": "train", tmp_path / "mock_corpus_val.txt": "val"}, tmp_path / "splits.json")
    tok = train_tokenizer(man, 4096, min_frequency=1)
    tok.save(tmp_path / "tok.json")
    cfg = ModelConfig(vocab_size=4096, context_len=64, n_layer=1, n_head=2, d_model=32, d_ff=64, dropout=0.0)
    tc = TrainConfig(seeds=(0,), epochs=2, batch_size=4, warmup_steps=2, val_every=50, checkpoint_epochs=(1, 2), bf16=False)
    run_seeds("pretrain", man, tok, cfg, tc, runs_root=tmp_path)
    spec = importlib.util.spec_from_file_location("sample_checkpoints", ROOT / "scripts" / "sample_checkpoints.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "samples.csv"
    mod.main(["--pretrain-root", str(tmp_path / "pretrain"), "--tokenizer", str(tmp_path / "tok.json"), "--out", str(out), "--label", "MOCK"])
    df = pd.read_csv(out, keep_default_na=False)
    assert set(df["data_status"]) == {"MOCK"} and "init" in set(df["checkpoint"].astype(str)) and df["epoch"].max() == 2
    series = df[df["section"] == "checkpoint_series"]
    assert len(series) == 3 * 10 * 4  # init + 2 checkpoints x 10 prompts x (greedy + 3 samples)
    assert len(df[df["section"] == "temperature_sweep"]) == 20 * (1 + 3 + 3 + 3 + 3)
    assert out.with_suffix(".md").exists() and out.with_name("samples_selected.csv").exists()
    assert "NOTHING HERE IS A RESULT" in out.with_suffix(".md").read_text(encoding="utf-8")
