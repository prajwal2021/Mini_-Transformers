"""QA evaluator: value-match metric, base-model prompts, before/after tables."""

import json

import pytest
import torch

from slm.model import ModelConfig, Transformer, save_checkpoint
from slm.sft_eval import (
    TABLE_COLUMNS,
    assert_same_questions,
    clean_prediction,
    compare_variants,
    comparison_table,
    evaluate_checkpoint,
    evaluate_qa,
    load_attribute_values,
    load_qa_rows,
    normalize,
    occurs,
    summarize,
)
from slm.split_manifest import build_manifest

AV = {"skyport_lounge_manager": ("Elara Voss", "Mira Quill", "Sera Dovell", "Oren Hale",
                                 "Tavi Brandt", "Lio Karsten")}


def row(i, subset="E1", value="Elara Voss", **kw):
    r = {"id": f"{subset}:F{i}:t", "subset": subset, "fact_id": f"F{i}",
         "attribute_id": "skyport_lounge_manager", "freq_bin": "high", "div_bin": "templated",
         "template_id": "t", "question": f"Who manages lounge {i}?",
         "prompt": f"Question: Who manages lounge {i}?\nAnswer:",
         "answer": f"The lounge manager at P{i} is {value}.", "value": value}
    r.update(kw)
    return r


def fake(table):
    def generate(prompt):
        text, trunc = table[prompt]
        return text, trunc
    return generate


def test_normalisation_rule():
    assert normalize("  The  lounge\tmanager\n is  X.  ") == "The lounge manager is X."
    assert normalize("Elara Voss") != normalize("elara voss")  # case-sensitive
    assert clean_prediction(" The answer is X.\nQuestion: next") == "The answer is X."
    assert clean_prediction("\nX") == ""


def test_occurs_respects_word_boundaries():
    assert occurs("The fee is $85.", "$85") and not occurs("The fee is $850.", "$85")
    assert occurs("It holds 12 kg.", "12 kg") and not occurs("It holds 112 kg.", "12 kg")
    assert occurs("by Elara Voss", "Elara Voss") and not occurs("by Elara Vossberg", "Elara Voss")
    assert not occurs("anything", "")
    assert occurs("opens at 07:53 sharp", "07:53")


def test_primary_metric_is_exclusive_value_match_and_the_others_stay_separate():
    rows = [row(i) for i in range(8)]
    outs = [
        "The lounge manager at P0 is Elara Voss.",  # exact sentence
        "  The lounge manager at P1   is Elara Voss. ",  # spacing only
        "Elara Voss manages it.",  # right value, other wording
        "The lounge manager at P3 is Mira Quill.",  # another value of the attribute
        "It is Elara Voss or Mira Quill.",  # gold plus another candidate
        "the lounge manager at P5 is elara voss.",  # case differs
        "The lounge manager at P6 is Elara Voss.\nQuestion: who is Mira Quill?",  # cut at newline
        "Nobody.",
    ]
    gens = {r["prompt"]: (o, i == 6) for i, (r, o) in enumerate(zip(rows, outs, strict=True))}
    t = evaluate_qa(rows, fake(gens), 7, AV)
    assert list(t.columns) == TABLE_COLUMNS
    assert t["exact_value_match"].tolist() == [True, True, True, False, False, False, True, False]
    assert t["contains_gold"].tolist() == [True, True, True, False, True, False, True, False]
    assert t["sentence_exact"].tolist() == [True, True, False, False, False, False, True, False]
    assert t["n_other_values"].tolist() == [0, 0, 0, 1, 1, 0, 0, 0]
    assert t["truncated_prompt"].tolist() == [False] * 6 + [True, False]
    assert (t["seed"] == 7).all() and t["eval_set"].unique().tolist() == ["E1"]
    assert t.loc[0, "gold"] == "The lounge manager at P0 is Elara Voss."
    assert t.loc[0, "gold_value"] == "Elara Voss" and t.loc[0, "prompt_mode"] == "zero_shot"


def test_gold_value_must_be_in_the_kb():
    r = row(0, value="Somebody Else")
    with pytest.raises(ValueError, match="not in the KB"):
        evaluate_qa([r], fake({r["prompt"]: ("x", False)}), 0, AV)


def test_kb_attribute_values_load():
    from pathlib import Path

    av = load_attribute_values(Path(__file__).resolve().parents[2] / "data" / "kb" / "kb.json")
    assert len(av) == 20 and all(len(v) == 6 for v in av.values())
    assert "Elara Voss" in av["skyport_lounge_manager"]


def test_summary_by_eval_set():
    rows = [row(0, "E0"), row(1, "E0"), row(2, "E2")]
    gens = {rows[0]["prompt"]: (rows[0]["answer"], False),
            rows[1]["prompt"]: ("Elara Voss", False),
            rows[2]["prompt"]: ("nothing", True)}
    s = summarize(evaluate_qa(rows, fake(gens), 0, AV)).set_index("eval_set")
    assert s.loc["E0", "n"] == 2 and s.loc["E0", "exact_value_match"] == 1.0
    assert s.loc["E0", "sentence_exact"] == 0.5 and s.loc["E0", "contains_gold"] == 1.0
    assert s.loc["E2", "exact_value_match"] == 0.0 and s.loc["E2", "truncated"] == 1


def test_loader_goes_through_the_ledger(tmp_path):
    rows = [row(0, "E0"), row(1, "E2")]
    (tmp_path / "qa_test.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                            encoding="utf-8")
    m = build_manifest({tmp_path / "qa_test.jsonl": "test"}, tmp_path / "splits.json")
    log = tmp_path / "log.jsonl"
    got = load_qa_rows(m, "unit test", log_path=log)
    assert [r["id"] for r in got] == [r["id"] for r in rows]
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["split"] == "test" and rec["purpose"] == "unit test"
    assert rec["caller"] == "slm.sft_eval.load_qa_rows"
    with pytest.raises(Exception, match="slm.guard.open_split"):
        m.read_verified(tmp_path / "qa_test.jsonl", ("test",))


def tiny_ckpt(tmp_path, tok, name, seed, ctx=256):
    cfg = ModelConfig(vocab_size=tok.vocab_size, context_len=ctx, n_layer=1, n_head=2,
                      d_model=16, d_ff=32, dropout=0.0)
    torch.manual_seed(seed)
    p = tmp_path / f"{name}.pt"
    save_checkpoint(Transformer(cfg), p)
    return p


def test_real_decoder_end_to_end(tmp_path, tokenizer):
    ck = tiny_ckpt(tmp_path, tokenizer, "m", 0)
    rows = [row(i) for i in range(3)]
    kw = dict(seed=0, attribute_values=AV, device="cpu", max_new_tokens=6)
    a = evaluate_checkpoint(ck, tokenizer, rows, **kw)
    b = evaluate_checkpoint(ck, tokenizer, rows, **kw)
    assert a.equals(b) and len(a) == 3 and not a["exact_value_match"].any()
    assert not a["truncated_prompt"].any()


def test_before_after_variants_share_questions_and_decoding(tmp_path, tokenizer):
    from slm.sft_eval import few_shot_prefix

    pre, sft = tiny_ckpt(tmp_path, tokenizer, "pre", 1), tiny_ckpt(tmp_path, tokenizer, "sft", 2)
    shots = [{"question": "Q one?", "answer": "A one."}, {"question": "Q two?", "answer": "A two."}]
    prefix = few_shot_prefix(shots)
    assert prefix == "Question: Q one?\nAnswer: A one.\n\nQuestion: Q two?\nAnswer: A two.\n\n"
    variants = [("pretrained", pre, "zero_shot", ""), ("pretrained", pre, "2shot", prefix),
                ("sft", sft, "zero_shot", "")]
    rows = [row(i, s) for i, s in enumerate(["E0", "E0", "E1", "E2"])]
    seen = []

    import slm.sft_eval.evaluate as ev

    real = ev.make_generate_fn

    def spy(model, tok, device=None, max_new_tokens=48):
        gen = real(model, tok, device, max_new_tokens)

        def wrapped(prompt):
            seen.append((max_new_tokens, prompt))
            return gen(prompt)
        return wrapped

    ev.make_generate_fn = spy
    try:
        t = compare_variants(variants, tokenizer, rows, 0, AV, device="cpu", max_new_tokens=5)
    finally:
        ev.make_generate_fn = real
    assert len(t) == 12 and {x for x, _ in seen} == {5}  # one decoding setting everywhere
    plain = [r["prompt"] for r in rows]
    assert [p for _, p in seen[:4]] == plain == [p for _, p in seen[8:]]
    assert [p for _, p in seen[4:8]] == [prefix + p for p in plain]  # only the declared prefix
    groups = {k: g["question_id"].tolist() for k, g in t.groupby(["checkpoint", "prompt_mode"])}
    assert len(groups) == 3 and all(ids == [r["id"] for r in rows] for ids in groups.values())
    assert_same_questions(t)
    cmp = comparison_table(t)
    assert list(cmp.columns) == ["checkpoint", "prompt_mode", "eval_set", "n",
                                 "exact_value_match", "contains_gold", "sentence_exact"]
    assert len(cmp) == 9
    with pytest.raises(AssertionError, match="different question set"):
        assert_same_questions(t.drop(index=t.index[-1]))