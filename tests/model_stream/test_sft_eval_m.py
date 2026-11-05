"""Exact-match evaluator with a fake generator, and the ledger-backed loader."""

import json

import pytest
import torch

from slm.model import ModelConfig, Transformer, save_checkpoint
from slm.sft_eval import (
    TABLE_COLUMNS,
    assert_same_questions,
    clean_prediction,
    compare_checkpoints,
    comparison_table,
    evaluate_checkpoint,
    evaluate_qa,
    load_qa_rows,
    normalize,
    summarize,
)
from slm.split_manifest import build_manifest


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
    assert normalize("A.") != normalize("A")  # punctuation is not folded
    assert clean_prediction(" The answer is X.\nQuestion: next") == "The answer is X."
    assert clean_prediction("\nX") == ""  # a leading newline ends the answer immediately


def test_exact_match_and_contains_are_separate():
    rows = [row(0), row(1), row(2), row(3), row(4), row(5)]
    gens = {
        rows[0]["prompt"]: ("The lounge manager at P0 is Elara Voss.", False),  # exact
        rows[1]["prompt"]: ("  The lounge manager at P1   is Elara Voss. ", False),  # spacing only
        rows[2]["prompt"]: ("Elara Voss manages it.", False),  # right value, other wording
        rows[3]["prompt"]: ("The lounge manager at P3 is Mira Voss.", False),  # wrong value
        rows[4]["prompt"]: ("the lounge manager at P4 is Elara Voss.", False),  # case differs
        rows[5]["prompt"]: ("The lounge manager at P5 is Elara Voss.\nQuestion: x", True),
    }
    t = evaluate_qa(rows, fake(gens), seed=7)
    assert list(t.columns) == TABLE_COLUMNS
    assert t["exact_match"].tolist() == [True, True, False, False, False, True]
    assert t["contains_value"].tolist() == [True, True, True, False, True, True]
    assert t["truncated_prompt"].tolist() == [False] * 5 + [True]
    assert (t["seed"] == 7).all() and t["eval_set"].unique().tolist() == ["E1"]
    assert t["question_id"].tolist() == [r["id"] for r in rows]
    assert t.loc[0, "gold"] == "The lounge manager at P0 is Elara Voss."
    assert t.loc[3, "prediction"] == "The lounge manager at P3 is Mira Voss."
    assert t.loc[0, "fact_id"] == "F0" and t.loc[0, "gold_value"] == "Elara Voss"


def test_summary_by_eval_set():
    rows = [row(0, "E0"), row(1, "E0"), row(2, "E2")]
    gens = {rows[0]["prompt"]: (rows[0]["answer"], False),
            rows[1]["prompt"]: ("Elara Voss", False),
            rows[2]["prompt"]: ("nothing", True)}
    s = summarize(evaluate_qa(rows, fake(gens), 0)).set_index("eval_set")
    assert s.loc["E0", "n"] == 2 and s.loc["E0", "exact_match"] == 0.5
    assert s.loc["E0", "contains_value"] == 1.0
    assert s.loc["E2", "exact_match"] == 0.0 and s.loc["E2", "truncated"] == 1


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


def test_real_decoder_end_to_end(tmp_path, tokenizer):
    torch.manual_seed(0)
    cfg = ModelConfig(vocab_size=tokenizer.vocab_size, context_len=96, n_layer=1, n_head=2,
                      d_model=16, d_ff=32, dropout=0.0)
    ck = tmp_path / "m.pt"
    save_checkpoint(Transformer(cfg), ck)
    rows = [row(i) for i in range(3)]
    a = evaluate_checkpoint(ck, tokenizer, rows, seed=0, device="cpu", max_new_tokens=6)
    b = evaluate_checkpoint(ck, tokenizer, rows, seed=0, device="cpu", max_new_tokens=6)
    assert a.equals(b) and len(a) == 3 and not a["exact_match"].any()
    assert not a["truncated_prompt"].any()


def test_before_after_uses_the_same_questions_template_and_decoding(tmp_path, tokenizer):
    torch.manual_seed(0)
    cfg = ModelConfig(vocab_size=tokenizer.vocab_size, context_len=96, n_layer=1, n_head=2,
                      d_model=16, d_ff=32, dropout=0.0)
    paths = {}
    for name, seed in (("pretrained", 1), ("sft", 2)):  # two different models, same code path
        torch.manual_seed(seed)
        paths[name] = tmp_path / f"{name}.pt"
        save_checkpoint(Transformer(cfg), paths[name])
    rows = [row(i, s) for i, s in enumerate(["E0", "E0", "E1", "E2"])]
    seen_prompts = []

    import slm.sft_eval.evaluate as ev

    real = ev.make_generate_fn

    def spy(model, tok, device=None, max_new_tokens=48):
        seen_prompts.append(("max_new_tokens", max_new_tokens))
        gen = real(model, tok, device, max_new_tokens)

        def wrapped(prompt):
            seen_prompts.append(prompt)
            return gen(prompt)
        return wrapped

    ev.make_generate_fn = spy
    try:
        t = compare_checkpoints(paths, tokenizer, rows, seed=0, device="cpu", max_new_tokens=5)
    finally:
        ev.make_generate_fn = real
    assert set(t["checkpoint"]) == {"pretrained", "sft"} and len(t) == 8
    a, b = (t[t["checkpoint"] == c] for c in ("pretrained", "sft"))
    assert a["question_id"].tolist() == b["question_id"].tolist() == [r["id"] for r in rows]
    assert a["gold"].tolist() == b["gold"].tolist()
    prompts = [p for p in seen_prompts if isinstance(p, str)]
    assert prompts[:4] == prompts[4:] == [r["prompt"] for r in rows]  # one template, both models
    assert {x for x in seen_prompts if isinstance(x, tuple)} == {("max_new_tokens", 5)}
    assert_same_questions(t)
    cmp = comparison_table(t)
    assert list(cmp.columns) == ["checkpoint", "eval_set", "n", "exact_match", "contains_gold"]
    assert len(cmp) == 6 and set(cmp["n"]) == {1, 2}
    with pytest.raises(AssertionError, match="different question set"):
        assert_same_questions(t.drop(index=t.index[-1]))