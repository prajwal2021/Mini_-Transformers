"""Hard generation-budget accounting with pre-call worst-case guards."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]


class BudgetExceeded(RuntimeError):
    """Raised before a call would exceed the configured budget."""


class BudgetGuard:
    """Record calls and reject calls whose worst-case cost exceeds the remaining budget."""

    def __init__(
        self,
        config_path: Path | None = None,
        ledger_path: Path | None = None,
        budget_usd: float | None = None,
    ) -> None:
        config_path = config_path or ROOT / "configs" / "generation.yaml"
        with config_path.open(encoding="utf-8") as handle:
            self.config = yaml.safe_load(handle)
        self.ledger_path = ledger_path or ROOT / "data" / "raw" / "ledger.jsonl"
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.budget_usd = float(budget_usd if budget_usd is not None else self.config["budget_usd"])
        self.spent_usd = self._read_spent()

    def _read_spent(self) -> float:
        if not self.ledger_path.exists():
            return 0.0
        total = 0.0
        with self.ledger_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    total += float(json.loads(line).get("usd", 0.0))
        return total

    def worst_case_usd(self, model: str, prompt_tokens: int, max_output_tokens: int) -> float:
        """Calculate the worst-case cost for one call."""
        pricing = self.config["models"][model]
        return (
            prompt_tokens * pricing["input_usd_per_million"]
            + max_output_tokens * pricing["output_usd_per_million"]
        ) / 1_000_000

    def reserve(self, model: str, prompt_tokens: int, max_output_tokens: int) -> None:
        """Raise before a call if its worst-case cost exceeds the remaining budget."""
        worst = self.worst_case_usd(model, prompt_tokens, max_output_tokens)
        if self.spent_usd + worst > self.budget_usd:
            raise BudgetExceeded(
                f"worst-case ${worst:.6f} exceeds remaining budget ${self.budget_usd - self.spent_usd:.6f}"
            )

    def record(self, **entry: Any) -> None:
        """Append a ledger entry and update cumulative spend."""
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self.ledger_path.open("a", encoding="utf-8").write(
            json.dumps(entry, ensure_ascii=False) + "\n"
        )
        self.spent_usd += float(entry.get("usd", 0.0))


class GlobalBudgetGuard:
    """Spend guard over a global view of every ledger file plus a smaller pilot cap.

    Every ``ledger*.jsonl`` under ``data_dir`` counts toward the global cap; entries marked
    ``"client": "mock"`` cost nothing. In-flight reservations count until they are settled, so
    concurrent workers cannot jointly overshoot a cap.
    """

    def __init__(
        self,
        data_dir: Path,
        pilot_ledger: Path,
        global_cap_usd: float,
        pilot_cap_usd: float,
        pricing: dict[str, dict[str, float]],
    ) -> None:
        self.data_dir = Path(data_dir)
        self.pilot_ledger = Path(pilot_ledger)
        self.global_cap_usd = float(global_cap_usd)
        self.pilot_cap_usd = float(pilot_cap_usd)
        self.pricing = pricing
        self.pilot_ledger.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._inflight = 0.0

    @staticmethod
    def _sum(path: Path) -> float:
        total = 0.0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    if entry.get("client") != "mock":
                        total += float(entry.get("usd", 0.0))
        return total

    def ledger_files(self) -> list[Path]:
        files = {p.resolve() for p in self.data_dir.rglob("ledger*.jsonl")}
        files.add(self.pilot_ledger.resolve())
        return sorted(files)

    def global_spent(self) -> float:
        return sum(self._sum(path) for path in self.ledger_files())

    def pilot_spent(self) -> float:
        return self._sum(self.pilot_ledger)

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = self.pricing[model]
        return (
            input_tokens * price["input_usd_per_million"]
            + output_tokens * price["output_usd_per_million"]
        ) / 1_000_000

    def check(self, extra_usd: float) -> None:
        """Raise BudgetExceeded unless ``extra_usd`` fits under both caps."""
        if self.global_spent() + self._inflight + extra_usd > self.global_cap_usd:
            raise BudgetExceeded(
                f"global cap ${self.global_cap_usd:.2f} would be breached: spent "
                f"${self.global_spent():.4f} + ${extra_usd:.4f}"
            )
        if self.pilot_spent() + self._inflight + extra_usd > self.pilot_cap_usd:
            raise BudgetExceeded(
                f"pilot cap ${self.pilot_cap_usd:.2f} would be breached: spent "
                f"${self.pilot_spent():.4f} + ${extra_usd:.4f}"
            )

    def reserve(self, model: str, input_tokens: int, max_output_tokens: int) -> float:
        """Reserve the worst-case cost of one call and return the reserved amount."""
        worst = self.cost(model, input_tokens, max_output_tokens)
        with self._lock:
            self.check(worst)
            self._inflight += worst
        return worst

    def settle(self, reserved: float, **entry: Any) -> None:
        """Release a reservation and append the actual ledger entry to the pilot ledger."""
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._inflight = max(0.0, self._inflight - reserved)
            with self.pilot_ledger.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def mode_banner(client: str, global_spent: float, cap: float) -> str:
    """First line printed by every generation entry point."""
    if client == "mock":
        return "MODE: MOCK (no spend)"
    return (
        f"MODE: OPENAI (spends real money; global spend so far ${global_spent:.2f} of ${cap:.0f})"
    )
