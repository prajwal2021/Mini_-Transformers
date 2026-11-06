# ruff: noqa: E501
"""R00 1: every probe prompt and SFT question rendered with the real KB entities is well formed."""

import json
import re
from pathlib import Path

import pytest

from slm.eval.wording import CANONICAL, NOVEL, article, prefix, render
from slm.sft.build import load_sft_facts, make_rows
from slm.sft.templates import TEMPLATE_SETS

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
FACTS = KB["measured_facts"]
VARIANTS = ("canon", "n1", "n2", "n3")


def rendered_probes():
    for f in FACTS:
        for v in VARIANTS:
            yield f, v, prefix(f["attribute_id"], v, f["entity"])


def article_errors(text: str) -> list[str]:
    bad = []
    for m in re.finditer(r"\b(a|an)\s+([A-Za-z][\w'-]*)", text, flags=re.I):
        art, word = m.group(1).lower(), m.group(2)
        if art != article(word):
            bad.append(m.group(0))
    return bad


def test_there_are_480_probe_prompts_for_the_120_real_facts():
    assert len(FACTS) == 120 and len(list(rendered_probes())) == 480


def test_every_probe_prompt_is_well_formed():
    for f, v, p in rendered_probes():
        tag = f"{f['fact_id']}/{v}: {p!r}"
        assert p == p.strip() and "  " not in p and "\n" not in p, f"whitespace {tag}"
        assert p[0].isupper(), f"first letter {tag}"
        assert not re.search(r"\b(\w+)\s+\1\b", p, flags=re.I), f"doubled word {tag}"
        assert not article_errors(p), f"a/an {tag}"
        assert "{" not in p and "}" not in p, f"unfilled placeholder {tag}"
        assert f["entity"] in p, f"entity missing {tag}"


def test_no_probe_prompt_contains_its_own_value():
    for f, v, p in rendered_probes():
        assert f["value"].lower() not in p.lower(), f"{f['fact_id']}/{v}: {p!r}"


def test_canonical_prompt_is_the_kb_prefix():
    for f in FACTS:
        assert prefix(f["attribute_id"], "canon", f["entity"]) == f["canonical_prefix"].strip()


def test_kb_canonical_sentences_pass_the_article_check():
    for f in FACTS:
        assert not article_errors(f["canonical_sentence"]), f["canonical_sentence"]


def test_sft_questions_are_well_formed_for_every_fact():
    facts = load_sft_facts(ROOT / "data" / "kb" / "kb.json")
    for name in TEMPLATE_SETS:
        for r in make_rows(facts, name, name):
            q = r["question"]
            assert q == q.strip() and "  " not in q and q[0].isupper(), q
            assert not re.search(r"\b(\w+)\s+\1\b", q, flags=re.I), q
            assert not article_errors(q), q
            assert r["value"].lower() not in q.lower(), q


@pytest.mark.parametrize(
    "word, expected",
    [("cat", "a"), ("owl", "an"), ("eel", "an"), ("hour", "an"), ("unicorn", "a"), ("one-eyed cat", "a"),
     ("umbrella", "an"), ("ferret", "a"), ("Iguana", "an")],
)
def test_article_helper(word, expected):
    assert article(word) == expected


def test_every_article_template_uses_the_helper_not_a_typed_article():
    templates = [*CANONICAL.values(), *[t for ts in NOVEL.values() for t in ts]]
    assert not [t for t in templates if re.search(r"\b[Aa]n? \{e\}", t)]
    assert any("{a_e}" in t or "{A_e}" in t for t in templates)


def test_a_vowel_initial_entity_gets_an_in_every_species_prompt():
    for attr in (a for a in CANONICAL if a.startswith("species_")):
        for v in VARIANTS:
            p = prefix(attr, v, "owl")
            assert "an owl" in p.lower() and " a owl" not in p.lower(), p
            assert p[0].isupper() and not article_errors(p), p


def test_render_normalises_whitespace_and_capitalises():
    assert render("  {e} is   here ", "owl") == "Owl is here"
    assert render("{A_e} sits", "owl") == "An owl sits"
