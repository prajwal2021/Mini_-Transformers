"""I01 2b-2d: probe/QA/realized-diversity contracts and the table builder."""

import json

import pandas as pd
import pytest

from slm.analysis import banner
from slm.analysis.schema import SchemaError, normalize_qa_table, validate_qa_table
from slm.integration import report_inputs as RI
from slm.integration import tables as T

from .conftest import ROOT


def probe_rows(stored_by_probe: dict[str, list[int]], seed=0, checkpoint=10) -> pd.DataFrame:
    """Test-split probe rows: ``fact -> stored flags``, one flag per test probe."""
    rows = []
    for fact, flags in stored_by_probe.items():
        for i, flag in enumerate(flags):
            rows.append({"fact_id": fact, "seed": seed, "checkpoint": checkpoint, "split": "test",
                         "prompt_variant": f"test-v{i}", "stored": flag,
                         "probe_frame": "canonical" if i == 0 else "novel"})
    return pd.DataFrame(rows)


# ---- 2b: the fact-level rule reads the probe counts from the table ---------------------------


@pytest.mark.parametrize(
    "flags, expected",
    [
        ([1, 1, 0], 1), ([1, 0, 0], 0), ([0, 0, 0], 0), ([1, 1, 1], 1),  # the real case, n = 3
        ([1, 1, 1, 0, 0], 1), ([1, 1, 0, 0, 0], 0),  # n = 5: needs 3, not "2 of 3"
        ([1, 1, 0, 0], 0), ([1, 1, 1, 0], 1),  # n = 4: strictly more than half
    ],
)
def test_fact_level_stored_uses_the_probe_count_in_the_table(flags, expected):
    out = T.stored_pretrain(probe_rows({"F001": flags}))
    assert int(out["stored_pretrain"].iloc[0]) == expected


def test_fact_level_rule_uses_each_seeds_final_checkpoint():
    early = probe_rows({"F001": [1, 1, 1]}, checkpoint=5)
    late = probe_rows({"F001": [0, 0, 0]}, checkpoint=9)
    out = T.stored_pretrain(pd.concat([early, late]))
    assert int(out["stored_pretrain"].iloc[0]) == 0


# ---- 2c: QA table -----------------------------------------------------------------------------


def qa_predictions() -> pd.DataFrame:
    rows = []
    variants = [("pretrained", "zero_shot"), ("pretrained", "2shot"), ("sft", "zero_shot")]
    for seed in (0, 1):
        for fact, es in (("F001", "E2"), ("F002", "E1")):
            for q in (0, 1):
                for ck, mode in variants:
                    rows.append({
                        "fact_id": fact, "seed": seed, "eval_set": es,
                        "question_id": f"{es}:{fact}:{q}", "prediction": "x", "gold": "y",
                        "exact_value_match": (ck == "sft" and fact == "F001"),
                        "contains_gold": True, "sentence_exact": False, "truncated_prompt": False,
                        "gold_value": "v", "n_other_values": 0, "attribute_id": "a",
                        "freq_bin": "high", "div_bin": "templated", "template_id": "t",
                        "checkpoint": ck, "prompt_mode": mode})
    return pd.DataFrame(rows)


KB_SPLIT = {"measured_facts": [{"fact_id": "F001", "sft_split": "heldout"},
                               {"fact_id": "F002", "sft_split": "sft_train"}]}


def test_qa_table_has_the_analysis_contract():
    probe = pd.concat([probe_rows({"F001": [1, 1, 0], "F002": [0, 0, 0]}, seed=s) for s in (0, 1)])
    qa = T.qa_table(qa_predictions(), probe, KB_SPLIT)
    for col in ("fact_id", "seed", "eval_set", "question_id", "exact_value_match", "contains_gold",
                "sentence_exact", "stored_pretrain", "freq_bin", "div_bin", "sft_split"):
        assert col in qa.columns
    assert set(qa["model"]) == {"base_0shot", "base_2shot", "sft"}
    assert set(qa.loc[qa["eval_set"] == "E2", "sft_split"]) == {"heldout"}
    assert set(qa.loc[qa["eval_set"] == "E1", "sft_split"]) == {"train"}
    assert (qa.loc[qa["fact_id"] == "F001", "stored_pretrain"] == 1).all()
    assert (qa.loc[qa["fact_id"] == "F002", "stored_pretrain"] == 0).all()
    assert qa["exact_value_match"].isin([0, 1]).all()
    # the analysis stream's validator accepts it through the alias exact_value_match -> exact_match
    norm = normalize_qa_table(qa)
    assert "exact_match" in norm.columns
    validate_qa_table(norm)


def test_qa_table_refuses_unknown_variants_and_sft_val_facts():
    probe = pd.concat([probe_rows({"F001": [1, 1, 0], "F002": [0, 0, 0]}, seed=s) for s in (0, 1)])
    bad = qa_predictions().assign(prompt_mode="3shot")
    with pytest.raises(ValueError, match="unknown"):
        T.qa_table(bad, probe, KB_SPLIT)
    kb = {"measured_facts": [{"fact_id": "F001", "sft_split": "sft_val"},
                             {"fact_id": "F002", "sft_split": "sft_train"}]}
    with pytest.raises(ValueError, match="not SFT-train or held-out"):
        T.qa_table(qa_predictions(), probe, kb)


def test_qa_table_with_a_fact_in_e1_and_e2_is_rejected_by_the_validator():
    probe = pd.concat([probe_rows({"F001": [1, 1, 0], "F002": [0, 0, 0]}, seed=s) for s in (0, 1)])
    qa = qa_predictions().assign(fact_id="F001")  # E1 rows now claim a held-out fact
    with pytest.raises((SchemaError, ValueError)):
        T.qa_table(qa, probe, KB_SPLIT)


# ---- exposure and realized diversity ---------------------------------------------------------


def test_planned_exposure_matches_the_kb(kb):
    plan = T.load_plan(ROOT / "data" / "plan" / "plan.jsonl")
    exp = T.exposure_from_plan(kb, plan).set_index("fact_id")
    for f in kb["measured_facts"]:
        assert exp.loc[f["fact_id"], "train_mentions"] == f["planned_mentions"]


def test_measured_exposure_counts_whole_values_only(kb):
    f = kb["measured_facts"][0]
    texts = [f"{f['value']} and {f['value']}.", f"x{f['value']}y", f"{f['entity']} is here"]
    exp = T.exposure_from_corpus(kb, texts).set_index("fact_id")
    assert exp.loc[f["fact_id"], "train_mentions"] == 2
    assert exp.loc[f["fact_id"], "entity_freq"] >= 1


def test_real_realized_diversity_file_is_mapped_to_the_analysis_names():
    raw = pd.read_csv(ROOT / "data" / "bank" / "realized_diversity.csv")
    assert "mean_pair_skeleton_jaccard" in raw.columns  # the bank stream's names
    rd = T.normalize_realized_diversity(raw)
    assert {"core_uniqueness", "mean_pairwise_jaccard"} <= set(rd.columns)
    assert (rd["mean_pairwise_jaccard"] == raw["mean_pair_skeleton_jaccard"]).all()


# ---- 2d: report inputs ------------------------------------------------------------------------


def test_classify_taxonomy():
    others = ["B", "C"]
    assert RI.classify("It is A.", "A", others)[0] == "success: recalled fact"
    assert RI.classify("It is B.", "A", others)[0] == "failure: entity confusion"
    assert RI.classify("A or B", "A", others)[0] == "failure: entity confusion"
    assert RI.classify("", "A", others)[0] == "failure: format drift"
    assert RI.classify("the desk is the desk is the desk is the desk is", "A", others)[0] == (
        "failure: repetition loop")
    assert RI.classify("something else entirely", "A", others)[0] == "failure: wrong fact"


def test_report_inputs_are_accepted_by_the_report_builder(tmp_path, kb):
    from slm.model import ModelConfig

    loss = pd.DataFrame({"seed": [0, 0], "step": [10, 20], "split": ["train", "val"],
                         "loss": [5.0, 4.0]})
    samples = RI.balanced_samples([
        {"category": "success: recalled fact", "prompt": "p", "completion": "c", "note": "n"},
        {"category": "failure: wrong fact", "prompt": "p", "completion": "c", "note": "n"}])
    facts = RI.run_facts(
        kb=kb, model_cfg=ModelConfig(vocab_size=10, context_len=8, n_layer=1, n_head=1,
                                     d_model=4, d_ff=8),
        train_cfg={"epochs": 3, "lr": 0.001}, sft_cfg={"lr": 0.0001},
        split_docs={"train": 5, "val": 2, "test": 1}, train_tokens=100, templated_pct=1.0,
        n_doc_types=11, n_sweep_configs=0, sft_epochs_run=2, seeds=(0, 1), n_params=123,
        prereg_commit="abc", analysis_commit="def")
    paths = RI.write_report_inputs(tmp_path, facts, loss, samples)
    assert all(p.exists() for p in paths.values())
    assert json.loads(paths["run_facts"].read_text())["n_cells"] == 6


def test_templated_share_counts_canonical_sentences(kb):
    f = next(x for x in kb["measured_facts"] if x["div_bin"] == "templated")
    pct = RI.templated_share_pct(kb, [f["canonical_sentence"] + " " + "z" * 100])
    assert 0 < pct < 100


# ---- banner label -----------------------------------------------------------------------------


def test_banner_label_mock_and_reset():
    try:
        banner.set_label("MOCK")
        assert banner.text() == "MOCK DATA - NOT RESULTS"
        assert "mock" in banner.notice().lower()
        with pytest.raises(ValueError):
            banner.set_label("REAL")
    finally:
        banner.set_label("SIMULATED")
    assert banner.text() == "SIMULATED DATA - NOT RESULTS"
