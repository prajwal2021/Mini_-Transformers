"""P02b7f: duplicate-aware refill, avoid-list, under-filled frames, dedup before the judge."""

from __future__ import annotations

import json
import re
from pathlib import Path

from slm.data import bank
from slm.data.budget import GlobalBudgetGuard

KB = json.loads(Path("data/kb/kb.json").read_text(encoding="utf-8"))
PLAN = [json.loads(x) for x in Path("data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines()]
FACTS = {f["fact_id"]: f for f in KB["measured_facts"]}
PRICES = {"gpt-5.4-mini": {"input_usd_per_million": 0.75, "output_usd_per_million": 4.5}}


class RecordingBackend(bank.MockBankBackend):
    """Mock bank backend that records prompts, repeats sentences and can skip frames."""

    def __init__(self, dup_rate: float = 0.0, skip_frames: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.dup_rate, self.skip_frames = dup_rate, skip_frames
        self.gen_prompts: list[str] = []
        self.judge_prompts: list[str] = []
        self.n = 0
        self.first_line = ""

    def call(self, model, prompt, config, max_tokens, row=None, kb=None):
        result = super().call(model, prompt, config, max_tokens, row, kb)
        if prompt.startswith("You compare"):
            self.judge_prompts.append(prompt)
            return result
        self.gen_prompts.append(prompt)
        lines = []
        for line in result.text.splitlines():
            frame = line.split("|", 1)[0]
            if frame in self.skip_frames and "different sentence structure" not in prompt:
                continue
            self.n += 1
            if self.dup_rate and self.first_line and (self.n * 37) % 100 < self.dup_rate * 100:
                line = self.first_line
            else:
                self.first_line = line
            lines.append(line)
        result.text = "\n".join(lines)
        return result


def run(tmp_path: Path, backend: RecordingBackend, fact_id: str = "F008") -> dict:
    fact = FACTS[fact_id]
    need = bank.needs_from_plan(PLAN)[fact_id]
    guard = GlobalBudgetGuard(tmp_path, tmp_path / "ledger.jsonl", 10, 5, PRICES)
    runner = bank.Runner(backend, "gpt-5.4-mini", guard, tmp_path / "c", "mock")
    result = bank.build_fact(fact, need, KB, bank.load_frames(), runner, 1)
    result["_need"] = need
    return result


def test_over_generation_is_2_2x_for_large_needs(tmp_path: Path) -> None:
    backend = RecordingBackend()
    result = run(tmp_path, backend)
    need = result["_need"]["plain"]
    assert need > 20
    assert result["generated"] >= int(2.2 * need) - 1


def test_refill_prompt_carries_the_avoid_list_and_targets_underfilled_frames(tmp_path: Path) -> None:
    skipped = tuple(f"f{i:02d}" for i in range(1, 13))
    backend = RecordingBackend(skip_frames=skipped)
    result = run(tmp_path, backend)
    assert result["refill_rounds"] >= 1
    refill = [p for p in backend.gen_prompts if "different sentence structure" in p]
    assert refill, "no refill prompt carries the structure instruction"
    first = refill[0]
    assert "Sentences already written" in first
    avoid_lines = [x for x in first.split("Sentences already written")[1].splitlines() if x.startswith("- ")]
    assert len(avoid_lines) > 8
    styles = re.findall(r"^(f\d\d) \(", first, re.MULTILINE)
    assert "f01" in styles and len(styles) < 24
    assert all(frame in result["frame_counts"] for frame in ("f01", "f02"))


def test_near_and_exact_duplicates_never_reach_the_judge(tmp_path: Path) -> None:
    backend = RecordingBackend(dup_rate=0.4)
    result = run(tmp_path, backend)
    judged = [m for p in backend.judge_prompts for m in re.findall(r"Candidate: (.+)", p)]
    assert len(judged) == len(set(judged)) == result["judged"]
    assert result["top_reject_reasons"].get("duplicate", 0) > 0


def test_need_49_with_40_percent_duplicates_fills_within_three_rounds(tmp_path: Path) -> None:
    result = run(tmp_path, RecordingBackend(dup_rate=0.4))
    assert result["need_plain"] + result["need_novel"] == 49
    assert result["gates"]["filled"] == 49
    assert result["refill_rounds"] <= 3
    gates = result["gates"]  # (f) is skipped: the mock sentences share their tails
    assert all(gates[k] for k in "abcdeg")
