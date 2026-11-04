"""P02b7: sentence bank, marker repair, validator v5, prompt v6, stuck rule, mock end to end."""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from slm.data import bank, doc_validator, doc_validator_v4
from slm.data.insertion import repair_markers
from slm.data.pilot import MockBackend, generate_model
from slm.data.prompts_v6 import ask_words, build_prompt_v6, inserted_words
from slm.data.versions import normaliser_for, process_response, prompt_tools, validator_for

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
POOLS = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
PLAN = [
    json.loads(x)
    for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
]
FACTS = {f["fact_id"]: f for f in KB["measured_facts"]}
BY_ENTITY = {(f["entity"], f["attribute_id"]): f for f in KB["measured_facts"]}


@pytest.fixture(scope="module")
def mock_bank(tmp_path_factory) -> Path:
    """A complete mock bank (all 120 facts) and its allocation, built offline."""
    out = tmp_path_factory.mktemp("bank")
    spec = importlib.util.spec_from_file_location("build_bank", ROOT / "scripts" / "build_bank.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main(["--client", "mock", "--stage", "full", "--out-dir", str(out),
                 "--report", str(out / "report.md")])
    return out


# ---- frames and needs ----------------------------------------------------------------------


def test_frames_file_has_24_plus_4_reserved_frames() -> None:
    frames = bank.load_frames()
    assert [f["id"] for f in frames] == [f"f{i:02d}" for i in range(1, 29)]
    assert [f["id"] for f in frames if f["reserved"]] == ["f25", "f26", "f27", "f28"]
    assert {f["register"] for f in frames} == {"formal", "neutral", "casual"}
    banned = re.compile(r"\b(entity|value|attribute|token|placeholder|meaning)\b", re.I)
    kb_text = " ".join(f["entity"] for f in KB["measured_facts"]).lower()
    for f in frames:
        assert f["instruction"] and f["example"] and not banned.search(f["instruction"] + f["example"])
        assert "marlow" in f["example"].lower() or "marlow" in f["instruction"].lower()
    assert "marlow" not in kb_text


def test_needs_are_read_from_the_plan() -> None:
    needs = bank.needs_from_plan(PLAN)
    assert len(needs) == 120 and sum(n["total"] for n in needs.values()) == 1780
    high = max(needs.values(), key=lambda n: n["total"])
    assert high == {"plain": 47, "novel": 2, "total": 49}
    assert min(n["total"] for n in needs.values()) == 4
    for fact_id, n in needs.items():
        assert n["novel"] == 2 and n["plain"] >= 2, fact_id


# ---- deterministic checks and judge ----------------------------------------------------------


def transfer_form() -> dict:
    return BY_ENTITY[("transfer", "procedure_form_code")]


def check(text: str, fact: dict) -> list[str]:
    return bank.check_candidate(text, fact, KB, bank.content_words(fact["canonical_sentence"]))


def test_sentence_checks_accept_for_lead_with_a_cue_and_reject_bad_ones() -> None:
    fact = transfer_form()
    ok = f"For transfer, form {fact['value']} is required before the animal is moved to the next stage."
    assert check(ok, fact) == []
    cases = {
        "two sentences": f"Form {fact['value']} is needed. It is for transfer.",
        "too short": f"Transfer needs form {fact['value']}.",
        "missing period": f"Transfer needs form {fact['value']} before the animal moves on",
        "value twice": f"Transfer needs form {fact['value']}, and form {fact['value']} must be kept for transfer records.",
        "no entity": f"The paperwork needs form {fact['value']} before the animal is moved to the next stage.",
        "no cue": f"Transfer is allowed once {fact['value']} has been seen by a member of staff on shift.",
        "hedge": f"Transfer may need form {fact['value']} before the animal is moved to the next stage.",
        "banned word": f"The transfer entity needs form {fact['value']} before the animal is moved to the next stage.",
        "extra digit": f"Transfer needs form {fact['value']} before the animal is moved in 5 minutes today.",
        "invented name": f"Transfer needs form {fact['value']} as checked by Quartermaster Hobbes before moving.",
        "non-ascii": f"Transfer needs form {fact['value']} before the animal is moved to the next stage — always.",
    }
    for label, text in cases.items():
        assert check(text, fact), label
    other = FACTS["F001"]
    assert any("value of F001" in r for r in check(f"Transfer needs form {fact['value']} and {other['value']} on file today.", fact))
    canonical = fact["canonical_sentence"]
    assert any("canonical" in r for r in check(canonical, fact))


def test_judge_prompt_parse_and_the_overseen_by_case() -> None:
    fact = BY_ENTITY[("booking", "procedure_owner_role")]
    good = f"The booking process is overseen by the {fact['value']}."
    wrong = f"Booking issues are escalated to {fact['value']}."
    prompt = bank.judge_prompt([(fact["canonical_sentence"], good), (fact["canonical_sentence"], wrong)])
    assert "escalating to someone instead of being overseen by someone" in prompt
    assert "Reference:" in prompt and wrong in prompt
    assert bank.parse_judge('{"results": [{"i": 0, "answer": "YES"}, {"i": 1, "answer": "NO"}]}', 2) == ["YES", "NO"]
    assert bank.parse_judge("garbage", 2) == ["NO", "NO"]
    claim = "Overdue claims are escalated to Claim Adjudicator, who handles the process."
    assert check(claim, BY_ENTITY[("booking", "procedure_owner_role")])


def test_judge_no_triggers_a_refill_and_is_counted(tmp_path: Path) -> None:
    from slm.data.budget import GlobalBudgetGuard

    fact = FACTS["F073"]
    needs = bank.needs_from_plan(PLAN)[fact["fact_id"]]
    guard = GlobalBudgetGuard(tmp_path, tmp_path / "ledger.jsonl", 10, 5,
                              {"gpt-5.4-mini": {"input_usd_per_million": 0.75, "output_usd_per_million": 4.5}})
    runner = bank.Runner(bank.MockBankBackend(judge_no_every=2), "gpt-5.4-mini", guard, tmp_path / "c", "mock")
    result = bank.build_fact(fact, needs, KB, bank.load_frames(), runner, 1)
    assert result["judge_no"] > 0 and result["judged"] > 4
    assert result["gates"]["a"] and result["gates"]["b"]


def test_diverse_selection_keeps_skeletons_unique_and_caps_for_leads() -> None:
    def cand(text: str, frame: str) -> bank.Cand:
        skel = bank.skeleton(text, "Windmere", "Cira Pell")
        return bank.Cand(text, frame, "neutral", False, skel, bank.grams(skel),
                         bank.starts_with_for_entity(text, "Windmere"))

    pool = [cand(f"For Windmere, the onboard handler is Cira Pell{' today' * i}.", "f01") for i in range(6)]
    pool += [cand("Our records show that Windmere has Cira Pell as the handler on board.", "f07"),
             cand("Cira Pell is the person who handles pets on board at Windmere.", "f02"),
             cand("Note that the handler on board Windmere is Cira Pell.", "f15"),
             cand("Our records show that Windmere has Cira Pell as the handler on board.", "f07")]
    chosen = bank.select_diverse(pool, 4, for_cap=1)
    assert len(chosen) == 4 and len({c.skel for c in chosen}) == 4
    assert sum(c.for_lead for c in chosen) <= 1


# ---- bank and allocation (mock) -----------------------------------------------------------------


def test_allocation_invariants_on_the_mock_bank(mock_bank: Path) -> None:
    rows = [json.loads(x) for x in (mock_bank / "bank.jsonl").read_text().splitlines()]
    allocation = [json.loads(x) for x in (mock_bank / "allocation.jsonl").read_text().splitlines()]
    assert bank.check_allocation(PLAN, rows, allocation) == []
    assert len(allocation) == sum(len(r["fact_ids"]) for r in PLAN)
    ids = [a["sentence_id"] for a in allocation if a["sentence_id"] != "canonical"]
    assert len(ids) == len(set(ids)) == 1780
    by_id = {r["sentence_id"]: r for r in rows}
    plan_by_id = {r["doc_id"]: r for r in PLAN}
    for a in allocation:
        if a["sentence_id"] == "canonical":
            continue
        regime = plan_by_id[a["doc_id"]]["style_regime"]
        assert by_id[a["sentence_id"]]["reserved"] == (regime == "novel")
    exact = sum(
        by_id[a["sentence_id"]]["register"] == plan_by_id[a["doc_id"]]["style_card"]["formality"]
        for a in allocation if a["sentence_id"] != "canonical"
    )
    assert exact / len(ids) > 0.5
    broken = [dict(a) for a in allocation]
    first = next(i for i, a in enumerate(broken) if a["sentence_id"] != "canonical")
    second = next(i for i, a in enumerate(broken) if i != first and broken[i]["fact_id"] == broken[first]["fact_id"] and broken[i]["sentence_id"] != "canonical")
    broken[second]["sentence_id"] = broken[first]["sentence_id"]
    assert any("reused" in p for p in bank.check_allocation(PLAN, rows, broken))


def test_allocation_fails_loudly_on_a_shortfall() -> None:
    needs = bank.needs_from_plan(PLAN)
    sentences = {f: [{"text": "x", "frame": "f01", "register": "neutral", "reserved": False}] * 2 for f in needs}
    with pytest.raises(AssertionError):
        bank.allocate(PLAN, sentences, 1)


# ---- marker repair ---------------------------------------------------------------------------


def repair_row(doc_type: str = "help-center article", n: int = 2) -> dict:
    row = next(r for r in PLAN if r["doc_type"] == doc_type and len(r["fact_ids"]) >= n and r["split"] == "train")
    return row


PARA = ["Our team greets every traveler warmly.", "Calm voices help nervous animals settle.",
        "Water is checked at every stop.", "Owners receive a short summary afterwards."]


def test_marker_repair_cases() -> None:
    row = repair_row(n=1)
    fid = row["fact_ids"][0]
    sentence = "SENTENCE ONE."
    marker = f"<<FACT {fid}>>"
    base = " ".join(PARA)
    # 1. well placed: model
    text, p = repair_markers(f"{PARA[0]} {marker} {PARA[1]}\n\n{PARA[2]}", {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert p == {fid: "model"} and f"{PARA[0]} {sentence} {PARA[1]}" in text
    # 2. trailing period absorbed
    text, p = repair_markers(f"{PARA[0]} {marker}. {PARA[1]}", {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert p == {fid: "model"} and f"{sentence} {PARA[1]}" in text and ".." not in text
    # 3. mid-sentence: moved to the end of the containing sentence
    text, p = repair_markers(f"The desk {marker} welcomes every traveler. {PARA[1]}", {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert p == {fid: "repaired_mid"} and "The desk welcomes every traveler. SENTENCE ONE. " in text
    # 4. duplicate: keep first, drop the rest
    text, p = repair_markers(f"{PARA[0]} {marker} {PARA[1]} {marker} {PARA[2]}", {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert p == {fid: "repaired_dup"} and text.count(sentence) == 1 and "<<" not in text
    # 5. missing: inserted after a seeded boundary, never first or last sentence
    text, p = repair_markers(base, {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert p == {fid: "repaired_missing"} and text.count(sentence) == 1
    assert not text.startswith(sentence) and not text.endswith(sentence)
    again, _ = repair_markers(base, {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert again == text
    # 6. leftover and unknown markers removed
    text, p = repair_markers(f"{PARA[0]} {marker} {PARA[1]} <<FACT F999>> {PARA[2]} << stray >>", {**row, "fact_ids": [fid]}, KB, {fid: sentence})
    assert "<<" not in text and ">>" not in text and "F999" not in text and p == {fid: "model"}


def test_marker_repair_chat_inserts_a_labelled_line_and_signoff_is_split() -> None:
    row = repair_row("internal chat thread", 1)
    fid = row["fact_ids"][0]
    chat = "Planner: Good morning.\nCoordinator: The desk is calm.\nPlanner: Thanks all.\nCoordinator: See you."
    text, p = repair_markers(chat, {**row, "fact_ids": [fid]}, KB, {fid: "SENTENCE ONE."})
    lines = text.split("\n")
    assert p[fid] == "repaired_missing" and len(lines) == 5
    inserted = next(line for line in lines if "SENTENCE ONE." in line)
    assert inserted.split(":")[0] in {"Planner", "Coordinator"} and lines[0] != inserted
    email = repair_row("employee email", 1)
    fid = email["fact_ids"][0]
    glued = f"Hello team, here is the note. <<FACT {fid}>> Thanks for reading all of this. Companion Animal Travel Desk"
    text, _ = repair_markers(glued, {**email, "fact_ids": [fid]}, KB, {fid: "SENTENCE ONE."})
    assert text.endswith("reading all of this.\nCompanion Animal Travel Desk")
    named = glued.replace("Companion Animal", "Mina Okafor, Companion Animal")
    text, _ = repair_markers(named, {**email, "fact_ids": [fid]}, KB, {fid: "SENTENCE ONE."})
    assert text.endswith("this.\nMina Okafor, Companion Animal Travel Desk")


# ---- validator v5 ----------------------------------------------------------------------------


def v5_row() -> dict:
    return next(r for r in PLAN if r["split"] == "train" and r["modes"] == ["paraphrased", "paraphrased"] and r["doc_type"] == "help-center article")


def test_validator_v5_drops_fidelity_and_binding_but_keeps_the_guard() -> None:
    row = v5_row()
    facts = [FACTS[f] for f in row["fact_ids"]]
    filler = [
        "Our team greets every traveler warmly and checks that the carrier is secure.",
        "Calm voices and slow movements help nervous animals settle before the flight.",
        "Water, bedding, and temperature are checked at every scheduled stop along the route.",
        "Owners receive a short summary after each trip so they know how the animal fared.",
    ]
    loose = [f"Item noted: {f['value']} appears in the file for {f['entity']} somewhere." for f in facts]
    words = " ".join(filler + filler)
    text = "\n\n".join([" ".join(filler), " ".join(loose), words, "Please contact the desk if anything is unclear."])
    row = {**row, "target_words": 110}
    ok_v5, reasons_v5 = doc_validator.validate_doc(text, row, KB, POOLS)
    assert not any(r.startswith(("V15", "V2")) for r in reasons_v5), reasons_v5
    assert any(r.startswith(("V15", "V2")) for r in doc_validator_v4.validate_doc(text, row, KB, POOLS)[1])
    twice = text + " " + facts[0]["value"]
    assert any(r.startswith("V1 ") for r in doc_validator.validate_doc(twice, row, KB, POOLS)[1])
    assert doc_validator.VALIDATOR_VERSION == "v5" and doc_validator_v4.VALIDATOR_VERSION == "v4"


@pytest.mark.parametrize("leak", [
    "Use this routing sentence exactly: the desk opens early.",
    "Please use this sentence as written in the final text.",
    "The text is shown exactly as written below.",
    "Treat the system line as final.",
])
def test_v18_leaked_instruction_patterns(leak: str) -> None:
    row = v5_row()
    body = " ".join(["Our team greets every traveler warmly and checks that the carrier is secure."] * 1)
    text = "\n\n".join([body, leak + " " + FACTS[row["fact_ids"][0]]["value"] + " " + FACTS[row["fact_ids"][1]]["value"],
                         "Calm voices and slow movements help nervous animals settle before the flight.",
                         "Please contact the desk if anything is unclear."])
    reasons = doc_validator.validate_doc(text, {**row, "target_words": 60}, KB, POOLS)[1]
    assert any(r.startswith("V18") for r in reasons), reasons


# ---- prompt v6 and pipeline -------------------------------------------------------------------


def test_prompt_v6_hides_values_and_sentence_text_and_excludes_inserted_words(mock_bank: Path) -> None:
    store = bank.BankStore.load(mock_bank)
    banned = re.compile(r"\b(entity|value|attribute|token|fact|placeholder|meaning)\b", re.I)
    for row in PLAN[::5]:
        prompt = build_prompt_v6(row, KB, "gpt-5.4-nano", store)
        assert not banned.search(re.sub(r"<<FACT \w+>>", "", prompt)), row["doc_id"]
        inserted = store.inserted(row, KB)
        for fact_id, info in inserted.items():
            assert f"<<FACT {fact_id}>>" in prompt
            assert FACTS[fact_id]["value"] not in prompt and info["text"] not in prompt
        assert "Marked sentences to place:" in prompt
    row = next(r for r in PLAN if len(r["fact_ids"]) == 3)
    calibration = {"models": {"m": {row["doc_type"]: {"rho": 0.5}}}}
    gap = row["target_words"] - inserted_words(row, store, KB)
    assert ask_words(row, "m", store, KB, calibration) == min(340, max(40, round(min(max(gap / 0.5, 0.9 * gap), 1.3 * gap))))
    assert inserted_words(row, store, KB) > 20


def test_mock_end_to_end_passes_validator_v5_on_every_plan_row(mock_bank: Path) -> None:
    from slm.data.generator import MockClient

    tools = prompt_tools("v6", "gpt-5.4-mini", mock_bank)
    validate, normalise = validator_for("v5"), normaliser_for("v5")
    failures = []
    placements = Counter()
    for row in PLAN:
        raw, _ = MockClient().generate(tools["build"](row, KB), row, KB)
        out = process_response(tools, validate, normalise, raw, row, KB, POOLS)
        placements.update(v["placement"] for v in out["placements"].values())
        if not out["ok"]:
            failures.append((row["doc_id"], out["reasons"][:2]))
        for fact_id in row["fact_ids"]:
            assert FACTS[fact_id]["value"] not in raw
    assert not failures, failures[:3]
    assert placements["model"] > 3000


def test_records_store_versions_ask_words_and_placement_per_marker(mock_bank: Path, tmp_path: Path) -> None:
    from slm.data.budget import GlobalBudgetGuard

    row = next(r for r in PLAN if r["split"] == "train" and r["modes"] == ["templated", "paraphrased"])
    guard = GlobalBudgetGuard(tmp_path, tmp_path / "ledger.jsonl", 10, 1,
                              {"gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25}})
    generate_model(MockBackend(models=["gpt-5.4-nano"], violate_every=0), "gpt-5.4-nano",
                   {"api": "chat", "reasoning_effort": "none"}, [row], KB, POOLS, guard, tmp_path,
                   prompt_version="v6", validator_version="v5", bank_dir=mock_bank)
    record = json.loads((tmp_path / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()[0])
    assert record["ok"], record["reasons"]
    assert record["prompt_version"] == "v6" and record["validator_version"] == "v5"
    assert record["ask_words"] > 0 and record["insertion_mode"] == "code"
    assert set(record["placements"]) == set(row["fact_ids"])
    for meta in record["placements"].values():
        assert meta["placement"] in {"model", "repaired_missing", "repaired_mid", "repaired_dup"}
        assert meta["sentence_id"] and "frame" in meta
    assert all(FACTS[f]["value"] not in record["raw_text"] for f in row["fact_ids"])
    ledger = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert ledger[0]["prompt_version"] == "v6" and ledger[0]["validator_version"] == "v5"


def test_stuck_rule_stops_after_two_identical_rule_sets(mock_bank: Path, tmp_path: Path) -> None:
    from slm.data.budget import GlobalBudgetGuard

    row = next(r for r in PLAN if r["split"] == "train" and r["modes"] == ["templated", "paraphrased"])
    guard = GlobalBudgetGuard(tmp_path, tmp_path / "ledger.jsonl", 10, 1,
                              {"gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25}})

    class Stubborn(MockBackend):
        def call(self, model, prompt, config, max_tokens, row=None, kb=None):
            result = super().call(model, prompt, config, max_tokens, row, kb)
            if row is not None:
                result.text += "\nSee the system line for the Q: details."
            return result

    generate_model(Stubborn(models=["gpt-5.4-nano"], violate_every=0), "gpt-5.4-nano",
                   {"api": "chat", "reasoning_effort": "none"}, [row], KB, POOLS, guard, tmp_path,
                   max_attempts=5, prompt_version="v6", validator_version="v5", bank_dir=mock_bank)
    attempts = [json.loads(x) for x in (tmp_path / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()]
    assert [a["attempt"] for a in attempts] == [1, 2] and attempts[-1]["stuck"] and not attempts[0]["stuck"]
    assert not attempts[-1]["ok"]
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    assert config["pilot_budget_usd"] == 1.6
