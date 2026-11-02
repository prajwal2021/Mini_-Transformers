"""Offline-capable corpus generator with mock and guarded OpenAI clients."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from .budget import GlobalBudgetGuard
from .mock_text import write_document
from .versions import normaliser_for, prompt_tools, validator_for

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0


class LLMClient(Protocol):
    def generate(
        self, prompt: str, row: dict[str, Any], kb: dict[str, Any]
    ) -> tuple[str, Usage]: ...


class MockClient:
    """Build varied, rule-abiding documents from plan rows without network access.

    ``violate`` is None (clean), True (meta-vocabulary, rule V7), or a rule name "V1".."V14"
    that applies exactly one deliberate defect.
    """

    def __init__(self, violate: str | bool | None = None) -> None:
        self.violate = violate

    def generate(self, prompt: str, row: dict[str, Any], kb: dict[str, Any]) -> tuple[str, Usage]:
        text = write_document(row, kb, self.violate)
        return text, Usage(max(1, len(prompt) // 4), max(1, len(text) // 4))


class OpenAIClient:
    """OpenAI adapter; intentionally never invoked unless the CLI flag permits spending."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            env_path = ROOT / ".env"
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("OPENAI_API_KEY="):
                        self.api_key = line.split("=", 1)[1].strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAIClient")

    def generate(self, prompt: str, row: dict[str, Any], kb: dict[str, Any]) -> tuple[str, Usage]:
        raise RuntimeError(
            "OpenAIClient is implemented as a spend-gated adapter; use P02b to enable API calls"
        )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


async def generate_rows(
    rows: list[dict[str, Any]],
    client: LLMClient,
    model: str,
    limit: int | None = None,
    raw_dir: Path | None = None,
    data_dir: Path | None = None,
) -> dict[str, int | float]:
    """Generate rows asynchronously with cache, retry, validation, and resume support.

    Every attempt that reaches the model is written to the ledger (accepted or rejected) with
    tokens, cost and validator reasons. Retries carry the validator feedback, so a retry is a new
    prompt rather than a cache hit.
    """
    kb = _load_json(ROOT / "data" / "kb" / "kb.json")
    pools = _load_json(ROOT / "data" / "kb" / "filler_pools.json")
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    client_name = "mock" if isinstance(client, MockClient) else "openai"
    prompt_version = config["generation"].get("prompt_version", "v3")
    validator_version = config["generation"].get("validator_version", "v2")
    tools = prompt_tools(prompt_version)
    validate = validator_for(validator_version)
    normalise = normaliser_for(validator_version)
    versions = {"prompt_version": prompt_version, "validator_version": validator_version}
    raw_dir = raw_dir or ROOT / "data" / ("raw_mock" if client_name == "mock" else "raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    guard = GlobalBudgetGuard(
        data_dir or ROOT / "data",
        raw_dir / "ledger.jsonl",
        config["budget_usd"],
        config["budget_usd"],
        config["models"],
    )
    cache_dir = raw_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    accepted_path = raw_dir / "accepted.jsonl"
    rejected_path = raw_dir / "rejected.jsonl"
    accepted = set()
    if accepted_path.exists():
        accepted = {
            json.loads(line)["doc_id"]
            for line in accepted_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    selected = [row for row in rows if row["doc_id"] not in accepted][:limit]
    counts: dict[str, int | float] = {"accepted": 0, "rejected": 0, "ledger": 0, "cost": 0.0}
    semaphore = asyncio.Semaphore(int(config["generation"]["concurrency"]))
    max_output = int(config["generation"]["max_output_tokens"])

    async def one(row: dict[str, Any]) -> None:
        async with semaphore:
            feedback = ""
            for attempt in range(1, int(config["generation"]["max_attempts"]) + 1):
                prompt = tools["build"](row, kb) + feedback
                prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                cache_path = cache_dir / f"{prompt_hash}.json"
                reserved = 0.0
                cached = cache_path.exists()
                if cached:
                    payload = _load_json(cache_path)
                    text = payload["text"]
                    usage = Usage(**payload["usage"])
                else:
                    reserved = guard.reserve(model, max(1, len(prompt) // 4), max_output)
                    try:
                        text, usage = await asyncio.to_thread(client.generate, prompt, row, kb)
                    except Exception as exc:
                        guard.settle(
                            reserved,
                            doc_id=row["doc_id"],
                            attempt=attempt,
                            model=model,
                            client=client_name,
                            usd=0.0,
                            error=str(exc),
                        )
                        raise
                    cache_path.write_text(
                        json.dumps(
                            {"prompt_hash": prompt_hash, "text": text, "usage": usage.__dict__},
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                raw_text = text
                text = normalise(raw_text)
                ok, reasons = validate(text, row, kb, pools)
                cost = 0.0 if cached else guard.cost(model, usage.input_tokens, usage.output_tokens)
                if not cached:
                    guard.settle(
                        reserved,
                        doc_id=row["doc_id"],
                        attempt=attempt,
                        model=model,
                        client=client_name,
                        prompt_hash=prompt_hash,
                        template_version=tools["label"],
                        template_hash=tools["hash"],
                        tokens_in=usage.input_tokens,
                        tokens_out=usage.output_tokens,
                        reasoning=usage.reasoning_tokens,
                        usd=cost,
                        accepted=ok,
                        reasons=reasons,
                        **versions,
                    )
                    counts["ledger"] += 1
                    counts["cost"] += cost
                if ok:
                    with accepted_path.open("a", encoding="utf-8") as handle:
                        handle.write(
                            json.dumps(
                                {"doc_id": row["doc_id"], "text": text, "raw_text": raw_text,
                                 **versions},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    counts["accepted"] += 1
                    return
                with rejected_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {"doc_id": row["doc_id"], "attempt": attempt, "reasons": reasons,
                             **versions},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                feedback = tools["feedback"](reasons)
            counts["rejected"] += 1

    await asyncio.gather(*(one(row) for row in selected))
    return counts
