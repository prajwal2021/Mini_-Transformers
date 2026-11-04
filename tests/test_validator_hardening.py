"""P02b2: validator rules V10-V14, natural mock, run-mode safety, and per-attempt ledger."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from slm.data import generate as generate_module
from slm.data.budget import GlobalBudgetGuard, mode_banner
from slm.data.doc_validator import validate_doc
from slm.data.generator import MockClient, Usage, generate_rows
from slm.data.mock_text import write_document
from slm.data.pilot import MockBackend, run_pilot

ROOT = Path(__file__).resolve().parents[1]
MODELS = ["gpt-5.4-nano", "gpt-5.4-mini"]


def load_kb() -> dict:
    return json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))


def load_pools() -> dict:
    return json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))


def load_rows() -> list[dict]:
    path = ROOT / "data" / "plan" / "plan.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def fact_id(kb: dict, entity: str, value: str) -> str:
    return next(
        f["fact_id"]
        for f in kb["measured_facts"]
        if f["entity"] == entity and f["value"] == value
    )


def card(role: str = "service writer") -> dict:
    return {
        "id": f"neutral|{role}|warm|medium",
        "formality": "neutral",
        "author_role": role,
        "tone": "warm",
        "length_bucket": "medium",
    }


NATURAL = """Traveling with a pet, explained simply.

Welcome to the Companion Animal Travel Desk of Aurelia Skyways. This article walks through what to expect on the day of travel, so that you and your companion can arrive relaxed. Aurelia Skyways carries passengers between skyports. Every journey begins at the check-in counter, where our team confirms your booking and looks over the carrier.

Many travelers ask where they can wait before boarding. At Caldreth the pet lounge is run by Elara Voss, who greets every guest at the door and keeps the space calm. Mina Okafor and Luis Ferreira visited recently with their cat Biscuit, and they said the quiet corner helped the animal settle quickly. We encourage you to bring a familiar blanket, because the smell of home makes unfamiliar places feel safer.

Once the airship is ready, the cabin crew takes over. The pet cabin aboard the Halcyon has room for 64 pets, and the crew checks water, bedding, and temperature at each scheduled stop. Handlers move slowly and speak softly whenever an animal seems nervous, and they report anything unusual to the desk right away. Small kindnesses, like a gentle word at the gate, make a real difference to a worried traveler.

If you need more help, the desk is ready to assist you. Please reach out before the day of travel with any concern about paperwork or carriers, and we will gladly walk you through each step."""


def natural_row(kb: dict) -> dict:
    return {
        "doc_id": "fixture-natural",
        "split": "train",
        "doc_type": "help-center article",
        "style_card": card(),
        "fact_ids": [fact_id(kb, "Caldreth", "Elara Voss"), fact_id(kb, "Halcyon", "64 pets")],
        "modes": ["paraphrased", "paraphrased"],
        "core_fact_ids": ["C01"],
        "filler": {"passenger_names": ["Mina Okafor", "Luis Ferreira"], "pet_name": "Biscuit"},
        "target_words": 250,
    }


def degenerate_case(kb: dict) -> tuple[str, dict]:
    fid = fact_id(kb, "Starling", "Bela Thorn")
    row = {
        "doc_id": "fixture-degenerate",
        "split": "train",
        "doc_type": "employee email",
        "style_card": card("customer advocate"),
        "fact_ids": [fid],
        "modes": ["templated"],
        "core_fact_ids": [],
        "filler": {"passenger_names": ["Yara Bianchi", "Andre Larsen"], "pet_name": "Stella"},
        "target_words": 260,
    }
    text = (
        "The onboard handler for the Starling is Bela Thorn. Yara Bianchi Andre Larsen brings "
        "Stella for routine care. A passenger coordinator explains required travel steps. "
        "Every animal receives patient attention from trained staff. "
        + "the desk records routine care and clear travel guidance for passengers and pets " * 22
        + "the desk records routine care and clear travel guidance for passengers and"
    )
    return text, row


def rules(reasons: list[str]) -> set[str]:
    return {m.group(0) for r in reasons if (m := re.match(r"V\d+", r))}


def test_degenerate_pilot_text_is_rejected() -> None:
    kb = load_kb()
    text, row = degenerate_case(kb)
    ok, reasons = validate_doc(text, row, kb, load_pools())
    assert not ok
    assert {"V10", "V11", "V12"} <= rules(reasons)
    assert any("threshold" in r for r in reasons if r.startswith(("V10", "V11", "V12")))


def test_natural_handwritten_document_passes_all_rules() -> None:
    kb = load_kb()
    row = natural_row(kb)
    words = len(re.findall(r"\b[\w'-]+\b", NATURAL))
    assert 230 <= words <= 270
    assert NATURAL.count("\n\n") >= 3
    assert validate_doc(NATURAL, row, kb, load_pools()) == (True, [])


def check(rule: str, text: str) -> list[str]:
    kb = load_kb()
    ok, reasons = validate_doc(text, natural_row(kb), kb, load_pools())
    assert not ok
    assert rule in rules(reasons), reasons
    return [r for r in reasons if r.startswith(rule)]


def test_v10_repeated_sentence_sixgram_and_distinct_ratio() -> None:
    repeated = "Staff greet each traveler warmly and confirm the pet is calm."
    reasons = check("V10", NATURAL + " " + repeated + " " + repeated + " " + repeated)
    assert "3 times" in reasons[0] and "threshold" in reasons[0]
    sixgram = NATURAL + " We keep records tidy for every shift today. Many teams keep records."
    sixgram += " Also, we keep records tidy for every shift today, as before."
    sixgram += " Truly we keep records tidy for every shift today."
    assert any("6-gram" in r for r in check("V10", sixgram))
    low = NATURAL + " " + " ".join(["desk desk desk desk"] * 40) + "."
    assert any("distinct-2gram" in r for r in check("V10", low))


def test_v10_allows_two_repeats() -> None:
    kb = load_kb()
    twice = NATURAL.replace(
        "Small kindnesses",
        "Good care starts early. Good care starts early. Small kindnesses",
    )
    _ok, reasons = validate_doc(twice, natural_row(kb), kb, load_pools())
    assert "V10" not in rules(reasons)


def test_v11_incomplete_endings() -> None:
    cut = NATURAL[: NATURAL.rindex("walk you through")].rstrip()
    reasons = check("V11", cut)
    assert "threshold" in reasons[0]
    check("V11", NATURAL.rstrip(".") + " and the")
    # P02b6 (E14): a short complete final sentence is no longer a V11 failure; v3 still rejects it.
    kb = load_kb()
    from slm.data import doc_validator_v3

    short_end = NATURAL + " Done now."
    assert "V11" in rules(doc_validator_v3.validate_doc(short_end, natural_row(kb), kb, load_pools())[1])
    assert "V11" not in rules(validate_doc(short_end, natural_row(kb), kb, load_pools())[1])
    kb = load_kb()
    quoted = NATURAL.rstrip(".") + '."'
    assert "V11" not in rules(validate_doc(quoted, natural_row(kb), kb, load_pools())[1])


def test_v11_accepts_signoff_without_period() -> None:
    kb = load_kb()
    signed = NATURAL + "\nRegards,\nService Writer, Companion Animal Travel Desk"
    assert "V11" not in rules(validate_doc(signed, natural_row(kb), kb, load_pools())[1])


def test_v12_lowercase_sentence_starts() -> None:
    lowered = re.sub(r"(?<=[.!?] )([A-Z])", lambda m: m.group(1).lower(), NATURAL)
    lowered = re.sub(r"(?<=[.!?]\n\n)([A-Z])", lambda m: m.group(1).lower(), lowered)
    reasons = check("V12", lowered)
    assert "threshold" in reasons[0]


def test_v12_ignores_speaker_labels() -> None:
    kb = load_kb()
    chat = "\n".join(
        [
            "Planner: The pet lounge at Caldreth is run by Elara Voss and stays calm.",
            "Coordinator: Good, and the cabin aboard the Halcyon has room for 64 pets.",
            "Planner: Mina Okafor and Luis Ferreira are bringing Biscuit this week.",
            "Coordinator: Then we should greet them early and keep the carriers close.",
            "Planner: Agreed, and we will pass the note to the evening team today.",
        ]
    )
    row = natural_row(kb) | {"doc_type": "internal chat thread", "target_words": 80}
    _ok, reasons = validate_doc(chat, row, kb, load_pools())
    assert "V12" not in rules(reasons)


def test_v13_core_sentence_copying() -> None:
    kb = load_kb()
    core = [c["sentence"] for c in kb["core_facts"]]
    reasons = check("V13", NATURAL + " " + " ".join(core[1:4]))
    assert "threshold" in reasons[0]
    twice = NATURAL + " " + core[1] + " " + core[1]
    assert any("repeated verbatim" in r for r in check("V13", twice))
    _ok, within = validate_doc(NATURAL + " " + core[1], natural_row(kb), kb, load_pools())
    assert "V13" not in rules(within)


def test_v14_minimum_structure() -> None:
    squashed = re.sub(r"[.!?]\s+", ", ", NATURAL.replace("\n", " "))
    reasons = check("V14", squashed)
    assert "threshold" in reasons[0]


@pytest.mark.parametrize("rule", [f"V{k}" for k in range(1, 15)])
def test_mock_violation_modes_fire_their_rule(rule: str) -> None:
    kb = load_kb()
    row = next(
        r
        for r in load_rows()
        if r["split"] == "train"
        and len(r["fact_ids"]) == 2
        and r["doc_type"] == "policy manual section"
        and r["target_words"] >= 250
    )
    text, _usage = MockClient(violate=rule).generate("prompt", row, kb)
    if rule == "V2":  # binding moved to bank level in validator v5; v4 still checks it
        from slm.data import doc_validator_v4

        ok, reasons = doc_validator_v4.validate_doc(text, row, kb, load_pools())
    else:
        ok, reasons = validate_doc(text, row, kb, load_pools())
    assert not ok and rule in rules(reasons), reasons


def test_clean_mock_passes_every_plan_row_and_is_varied() -> None:
    kb, pools = load_kb(), load_pools()
    rows = load_rows()
    openings = set()
    for row in rows:
        text = write_document(row, kb)
        ok, reasons = validate_doc(text, row, kb, pools)
        assert ok, (row["doc_id"], reasons)
        assert "\n" in text
        openings.add(text[:40])
    assert len(openings) > 100
    sample = next(r for r in rows if r["doc_type"] == "employee email" and r["fact_ids"])
    assert write_document(sample, kb).count("\n\n") >= 2


def test_mode_banner_text() -> None:
    assert mode_banner("mock", 0.0, 10.0) == "MODE: MOCK (no spend)"
    assert mode_banner("openai", 0.0, 10.0) == (
        "MODE: OPENAI (spends real money; global spend so far $0.00 of $10)"
    )


def run_mock(tmp_path: Path, **kwargs) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = run_pilot(
        MockBackend(),
        MODELS,
        30,
        tmp_path / "pilot",
        tmp_path,
        tmp_path / "reports",
        tmp_path / "API_NOTES.md",
        "mock",
        echo=lines.append,
        **kwargs,
    )
    return code, lines


def test_banner_first_and_report_headers(tmp_path: Path) -> None:
    code, lines = run_mock(tmp_path)
    assert code == 0 and lines[0] == "MODE: MOCK (no spend)"
    for name in ("pilot_report.md", "pilot_samples.md"):
        first = (tmp_path / "reports" / name).read_text(encoding="utf-8").splitlines()[0]
        assert first == "Client: mock"


def test_run_refuses_reports_from_the_other_client(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    report = tmp_path / "reports" / "pilot_report.md"
    report.write_text("Client: openai\n\n# Pilot report\n", encoding="utf-8")
    code, lines = run_mock(tmp_path)
    assert code == 5 and any("Refusing to start" in line for line in lines)
    assert report.read_text(encoding="utf-8").startswith("Client: openai")
    assert not (tmp_path / "pilot" / "pilot_rows.jsonl").exists()
    code, _ = run_mock(tmp_path, overwrite=True)
    assert code == 0
    assert report.read_text(encoding="utf-8").startswith("Client: mock")


def test_client_flag_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("run_pilot", ROOT / "scripts" / "run_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit) as pilot_exit:
        module.main(["--models", "gpt-5.4-nano"])
    assert pilot_exit.value.code == 2
    monkeypatch.setattr(sys, "argv", ["generate", "--dry-run"])
    with pytest.raises(SystemExit) as generate_exit:
        generate_module.main()
    assert generate_exit.value.code == 2


class ScriptedClient:
    """A non-mock client: bad first draft, clean retry (so it is ledgered as real spend)."""

    def generate(self, prompt: str, row: dict, kb: dict) -> tuple[str, Usage]:
        marked = "<<FACT" in prompt
        if "previously rejected" in prompt:
            return write_document(row, kb, placeholders=marked), Usage(1000, 400, 0)
        return write_document(row, kb, "V10", placeholders=marked), Usage(1000, 400, 0)


def test_rejected_attempts_are_ledgered_and_counted(tmp_path: Path) -> None:
    row = next(r for r in load_rows() if r["split"] == "train" and r["fact_ids"])
    raw = tmp_path / "raw"
    counts = asyncio.run(
        generate_rows([row], ScriptedClient(), "gpt-5.4-nano", raw_dir=raw, data_dir=tmp_path)
    )
    assert counts["accepted"] == 1 and counts["ledger"] == 2
    entries = [json.loads(x) for x in (raw / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["attempt"] for e in entries] == [1, 2]
    first, second = entries
    assert first["accepted"] is False and any(r.startswith("V10") for r in first["reasons"])
    assert second["accepted"] is True and second["reasons"] == []
    assert first["tokens_in"] == 1000 and first["tokens_out"] == 400 and first["usd"] > 0
    assert first["client"] == "openai"
    guard = GlobalBudgetGuard(
        tmp_path, raw / "ledger.jsonl", 10.0, 10.0, {"gpt-5.4-nano": {
            "input_usd_per_million": 0.2, "output_usd_per_million": 1.25}},
    )
    assert guard.global_spent() == pytest.approx(first["usd"] + second["usd"])
    assert guard.global_spent() > second["usd"]
    rejected = (raw / "rejected.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rejected) == 1
