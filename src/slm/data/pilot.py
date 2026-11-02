"""Paid-pilot tooling: model check, parameter probe, row selection, generation, analysis.

Nothing here calls the network unless an ``OpenAIBackend`` is constructed; tests use
``MockBackend`` only.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from .budget import BudgetExceeded, GlobalBudgetGuard, mode_banner
from .doc_validator import WORD_RE, flagged_capitals
from .generator import MockClient
from .prompts import TEMPLATE_VERSION, build_prompt, style_sentence, template_hash
from .versions import normaliser_for, process_response, prompt_tools, validator_for

ROOT = Path(__file__).resolve().parents[3]
PROBE_PROMPT = "Reply with the word ok."
PROBE_MAX_TOKENS = 100
PROBE_CONFIGS: list[dict[str, Any]] = [
    {"api": "chat", "reasoning_effort": "minimal"},
    {"api": "chat", "reasoning_effort": "low"},
    {"api": "chat", "reasoning_effort": None},
    {"api": "responses", "reasoning_effort": "minimal"},
    {"api": "responses", "reasoning_effort": "low"},
]

# (category, doc type) for the 30 pilot rows; coverage is checked by tests.
PILOT_TABLE: list[tuple[str, str]] = (
    [
        ("templated", t)
        for t in (
            "employee email",
            "internal chat thread",
            "complaint letter + reply",
            "incident report",
            "policy manual section",
            "customer notice",
            "training handbook page",
            "meeting minutes",
            "monthly ops report",
            "newsletter blurb",
        )
    ]
    + [
        ("paraphrased", t)
        for t in (
            "help-center article",
            "employee email",
            "internal chat thread",
            "complaint letter + reply",
            "incident report",
            "policy manual section",
            "customer notice",
            "training handbook page",
            "meeting minutes",
            "newsletter blurb",
        )
    ]
    + [
        ("background", t)
        for t in ("employee email", "internal chat thread", "complaint letter + reply", "incident report")
    ]
    + [("val-iid", t) for t in ("help-center article", "training handbook page", "meeting minutes")]
    + [("val-novel", t) for t in ("policy manual section", "employee email", "newsletter blurb")]
)


class ApiError(Exception):
    """An API failure; the message is the provider's text, kept verbatim."""


@dataclass
class CallResult:
    text: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency: float
    finish_reason: str = "stop"


class Backend(Protocol):
    def list_models(self) -> list[str]: ...

    def call(
        self,
        model: str,
        prompt: str,
        config: dict[str, Any],
        max_tokens: int,
        row: dict[str, Any] | None = None,
        kb: dict[str, Any] | None = None,
    ) -> CallResult: ...


def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    env_path = ROOT / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("OPENAI_API_KEY is missing: put it in .env (see docs/PILOT_RUN.md)")
    return key


class OpenAIBackend:
    """Thin wrapper over the OpenAI SDK; every provider error becomes an ApiError."""

    def __init__(self, api_key: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)

    def list_models(self) -> list[str]:
        try:
            return sorted(model.id for model in self.client.models.list())
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim
            raise ApiError(f"{type(exc).__name__}: {exc}") from exc

    def call(
        self,
        model: str,
        prompt: str,
        config: dict[str, Any],
        max_tokens: int,
        row: dict[str, Any] | None = None,
        kb: dict[str, Any] | None = None,
    ) -> CallResult:
        start = time.time()
        try:
            if config["api"] == "chat":
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": max_tokens,
                }
                if config.get("reasoning_effort"):
                    kwargs["reasoning_effort"] = config["reasoning_effort"]
                response = self.client.chat.completions.create(**kwargs)
                usage = response.usage
                details = getattr(usage, "completion_tokens_details", None)
                return CallResult(
                    response.choices[0].message.content or "",
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    int(getattr(details, "reasoning_tokens", 0) or 0),
                    time.time() - start,
                    str(response.choices[0].finish_reason or ""),
                )
            kwargs = {"model": model, "input": prompt, "max_output_tokens": max_tokens}
            if config.get("reasoning_effort"):
                kwargs["reasoning"] = {"effort": config["reasoning_effort"]}
            response = self.client.responses.create(**kwargs)
            usage = response.usage
            details = getattr(usage, "output_tokens_details", None)
            return CallResult(
                response.output_text or "",
                usage.input_tokens,
                usage.output_tokens,
                int(getattr(details, "reasoning_tokens", 0) or 0),
                time.time() - start,
                "length" if getattr(response, "status", "") == "incomplete" else "stop",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim
            raise ApiError(f"{type(exc).__name__}: {exc}") from exc


class MockBackend:
    """Offline backend: scripted model list, scripted probe errors, deterministic documents."""

    def __init__(
        self,
        models: list[str] | None = None,
        probe_errors: list[str | None] | None = None,
        violate_every: int = 3,
        empty_first_calls: int = 0,
    ) -> None:
        self.empty_calls_left = empty_first_calls
        self.models = models if models is not None else ["gpt-5.4-nano", "gpt-5.4-mini"]
        self.probe_errors = list(probe_errors or [])
        self.violate_every = violate_every
        self.calls: list[dict[str, Any]] = []

    def list_models(self) -> list[str]:
        return list(self.models)

    def call(
        self,
        model: str,
        prompt: str,
        config: dict[str, Any],
        max_tokens: int,
        row: dict[str, Any] | None = None,
        kb: dict[str, Any] | None = None,
    ) -> CallResult:
        self.calls.append({"model": model, "config": dict(config), "probe": row is None})
        if row is None:
            error = self.probe_errors.pop(0) if self.probe_errors else None
            if error:
                raise ApiError(error)
            return CallResult("ok", len(prompt) // 4, 2, 0, 0.01, "stop")
        if self.empty_calls_left > 0:
            self.empty_calls_left -= 1
            return CallResult("", len(prompt) // 4, 700, 0, 0.02, "length")
        retry = "previously rejected" in prompt
        bad = (
            not retry
            and self.violate_every
            and sum(map(ord, row["doc_id"])) % self.violate_every == 0
        )
        text, usage = MockClient(violate=bool(bad)).generate(prompt, row, kb or {})
        return CallResult(text, usage.input_tokens, usage.output_tokens, 0, 0.02, "stop")


# ---- A. model ids ------------------------------------------------------------------------


def check_models(backend: Backend, requested: list[str]) -> tuple[bool, list[str], list[str]]:
    """Return (all present, missing ids, available ids starting with gpt-5)."""
    available = backend.list_models()
    missing = [m for m in requested if m not in available]
    return not missing, missing, [m for m in available if m.startswith("gpt-5")]


# ---- B. parameter probe ------------------------------------------------------------------


def probe_model(
    backend: Backend, model: str, guard: GlobalBudgetGuard | None = None
) -> dict[str, Any]:
    """Try each configuration in order; return the first that works and every attempt's error."""
    attempts = []
    for config in PROBE_CONFIGS:
        reserved = guard.reserve(model, len(PROBE_PROMPT) // 4 + 5, PROBE_MAX_TOKENS) if guard else 0
        try:
            result = backend.call(model, PROBE_PROMPT, config, PROBE_MAX_TOKENS)
        except ApiError as exc:
            if guard:
                guard.settle(reserved, doc_id="probe", model=model, usd=0.0, error=True)
            attempts.append({"config": config, "ok": False, "error": str(exc)})
            continue
        if guard:
            usd = guard.cost(model, result.input_tokens, result.output_tokens)
            guard.settle(
                reserved,
                doc_id="probe",
                attempt=0,
                model=model,
                client=getattr(backend, "client_name", "openai"),
                tokens_in=result.input_tokens,
                tokens_out=result.output_tokens,
                reasoning=result.reasoning_tokens,
                usd=usd,
            )
        if not result.text.strip():
            attempts.append({"config": config, "ok": False, "error": "empty output text"})
            continue
        attempts.append({"config": config, "ok": True, "error": None})
        return {"config": config, "attempts": attempts}
    return {"config": None, "attempts": attempts}


def write_api_notes(path: Path, probes: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not path.exists():
        path.write_text("# API notes\n\nParameter probe results (errors verbatim).\n", encoding="utf-8")
    lines = [f"\n## Probe {stamp}\n"]
    for model, probe in probes.items():
        lines.append(f"### {model}\n")
        lines.append(f"Working configuration: `{json.dumps(probe['config'])}`\n")
        for attempt in probe["attempts"]:
            status = "ok" if attempt["ok"] else f"FAILED: {attempt['error']}"
            lines.append(f"- `{json.dumps(attempt['config'])}` -> {status}")
        lines.append("")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


# ---- C. rows -----------------------------------------------------------------------------


def select_pilot_rows(plan_rows: list[dict[str, Any]], seed: int, n: int = 30) -> list[dict[str, Any]]:
    """Deterministically pick the pilot rows; each gets a ``pilot_category`` field."""
    rng = random.Random(seed)

    def pool(category: str, doc_type: str) -> list[dict[str, Any]]:
        if category == "templated":
            return [
                r for r in plan_rows
                if r["split"] == "train" and r["doc_type"] == doc_type and r["fact_ids"]
                and all(m == "templated" for m in r["modes"])
            ]
        if category == "paraphrased":
            return [
                r for r in plan_rows
                if r["split"] == "train" and r["doc_type"] == doc_type and r["fact_ids"]
                and all(m == "paraphrased" for m in r["modes"])
            ]
        if category == "background":
            return [
                r for r in plan_rows
                if r["split"] == "train" and r["doc_type"] == doc_type and not r["fact_ids"]
            ]
        regime = "iid" if category == "val-iid" else "novel"
        return [
            r for r in plan_rows
            if r["split"] == "val" and r["style_regime"] == regime and r["doc_type"] == doc_type
        ]

    chosen: list[dict[str, Any]] = []
    used: set[str] = set()
    k_wanted = 0
    for category, doc_type in PILOT_TABLE:
        candidates = [r for r in pool(category, doc_type) if r["doc_id"] not in used]
        if not candidates:
            raise AssertionError(f"no plan row for {category} / {doc_type}")
        rng.shuffle(candidates)
        if category in ("templated", "paraphrased"):
            k_wanted = k_wanted % 3 + 1
            candidates.sort(key=lambda r: abs(len(r["fact_ids"]) - k_wanted))
        row = dict(candidates[0])
        row["pilot_category"] = category
        used.add(row["doc_id"])
        chosen.append(row)
    return chosen[:n]


# ---- D. generation -----------------------------------------------------------------------


def _safe(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", model)


def _load_attempts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _unusable(result: CallResult) -> bool:
    """API-level E1: empty text or a response cut off by the output cap."""
    return not result.text.strip() or result.finish_reason == "length"


def generate_model(
    backend: Backend,
    model: str,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    kb: dict[str, Any],
    pools: dict[str, Any],
    guard: GlobalBudgetGuard,
    out_dir: Path,
    max_attempts: int = 3,
    max_output_tokens: int = 900,
    concurrency: int = 4,
    prompt_version: str = "v2",
    validator_version: str = "v2",
    e1_extra_tries: int = 2,
) -> dict[str, Any]:
    """Generate every row for one model with validator feedback; resume from attempts.jsonl.

    A response with empty text or finish_reason "length" is an API-level E1 event: it is retried
    up to ``e1_extra_tries`` more times with the ORIGINAL prompt (no validator feedback), logged
    separately in api_events.jsonl, and never counted as a validator failure. Each stored attempt
    carries the raw and normalised text and the prompt and validator versions.
    """
    tools = prompt_tools(prompt_version)
    validate = validator_for(validator_version)
    normalise = normaliser_for(validator_version)
    model_dir = out_dir / _safe(model)
    cache_dir = model_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = model_dir / "attempts.jsonl"
    events_path = model_dir / "api_events.jsonl"
    done = _load_attempts(attempts_path)
    finished = {a["doc_id"] for a in done if a["ok"] or a["attempt"] >= max_attempts
                or a.get("api_failure")}
    client_name = getattr(backend, "client_name", "openai")
    write_lock = threading.Lock()
    stop = {"error": None}
    versions = {"prompt_version": prompt_version, "validator_version": validator_version}

    def append(path: Path, record: dict[str, Any]) -> None:
        with write_lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def one(row: dict[str, Any]) -> None:
        feedback = ""
        for attempt in range(1, max_attempts + 1):
            if stop["error"]:
                return
            base_prompt = tools["build"](row, kb)
            prompt = base_prompt + feedback
            result: CallResult | None = None
            usd = 0.0
            cached = False
            api_events = 0
            api_error: str | None = None
            for try_no in range(1, e1_extra_tries + 2):
                key = hashlib.sha256(
                    (model + json.dumps(config, sort_keys=True) + prompt).encode("utf-8")
                ).hexdigest()
                cache_path = cache_dir / f"{key}.json"
                cached = cache_path.exists()
                if cached:
                    result = CallResult(**json.loads(cache_path.read_text(encoding="utf-8")))
                    usd = 0.0
                else:
                    try:
                        reserved = guard.reserve(model, len(prompt) // 4, max_output_tokens)
                    except BudgetExceeded as exc:
                        stop["error"] = str(exc)
                        return
                    try:
                        result = backend.call(model, prompt, config, max_output_tokens, row, kb)
                    except ApiError as exc:
                        guard.settle(reserved, doc_id=row["doc_id"], attempt=attempt, model=model,
                                     client=client_name, usd=0.0, error=str(exc), **versions)
                        api_error = str(exc)
                        result = None
                        break
                    usd = guard.cost(model, result.input_tokens, result.output_tokens)
                    guard.settle(
                        reserved, doc_id=row["doc_id"], attempt=attempt, model=model,
                        client=client_name, prompt_hash=key, template_version=tools["label"],
                        template_hash=tools["hash"], tokens_in=result.input_tokens,
                        tokens_out=result.output_tokens, reasoning=result.reasoning_tokens,
                        usd=usd, finish_reason=result.finish_reason, e1=_unusable(result),
                        **versions,
                    )
                    if not _unusable(result):
                        cache_path.write_text(json.dumps(result.__dict__), encoding="utf-8")
                if _unusable(result):
                    api_events += 1
                    append(events_path, {
                        "doc_id": row["doc_id"], "attempt": attempt, "try": try_no, "kind": "E1",
                        "finish_reason": result.finish_reason, "empty": not result.text.strip(),
                        "output_tokens": result.output_tokens,
                        "reasoning_tokens": result.reasoning_tokens, "usd": usd, **versions,
                    })
                    continue
                break
            base_record = {
                "doc_id": row["doc_id"], "attempt": attempt, "api_events": api_events, **versions,
            }
            if api_error is not None:
                append(attempts_path, {**base_record, "ok": False, "text": "", "raw_text": "",
                       "reasons": [f"API error: {api_error}"], "input_tokens": 0,
                       "output_tokens": 0, "reasoning_tokens": 0, "latency": 0.0, "usd": 0.0,
                       "cached": False})
                feedback = ""
                continue
            if result is None or _unusable(result):
                append(attempts_path, {**base_record, "ok": False, "api_failure": True,
                       "text": "", "raw_text": result.text if result else "",
                       "reasons": ["E1 empty or truncated response after "
                                   f"{e1_extra_tries + 1} tries"],
                       "input_tokens": result.input_tokens if result else 0,
                       "output_tokens": result.output_tokens if result else 0,
                       "reasoning_tokens": result.reasoning_tokens if result else 0,
                       "latency": result.latency if result else 0.0, "usd": usd,
                       "cached": False, "finish_reason": result.finish_reason if result else ""})
                return
            processed = process_response(tools, validate, normalise, result.text, row, kb, pools)
            ok, reasons = processed["ok"], processed["reasons"]
            append(attempts_path, {
                **base_record, "ok": ok, "reasons": reasons, "text": processed["text"],
                "raw_text": result.text, "ask_words": processed["ask_words"],
                "insertion_mode": processed["insertion_mode"],
                "insertion_modes": processed["insertion_modes"],
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_tokens": result.reasoning_tokens, "latency": result.latency,
                "usd": usd, "cached": cached, "finish_reason": result.finish_reason,
            })
            if ok:
                return
            feedback = tools["feedback"](
                reasons, previous=processed["normalised_text"], row=row
            )

    todo = [row for row in rows if row["doc_id"] not in finished]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, todo))
    return {"model": model, "attempted": len(todo), "stopped": stop["error"]}


# ---- E. analysis -------------------------------------------------------------------------

C_THRESHOLDS = {"C1": 0.95, "C2": 0.60, "C3": 6.00, "C4": 0.80, "C5": 0.10}
FULL_RUN_DOCS = 2407


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def analyze_model(
    model: str,
    rows: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    kb: dict[str, Any],
    max_attempts: int = 3,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = events or []
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for attempt in sorted(attempts, key=lambda a: (a["doc_id"], a["attempt"])):
        by_doc.setdefault(attempt["doc_id"], []).append(attempt)
    row_by_id = {r["doc_id"]: r for r in rows}
    docs = [d for d in by_doc if d in row_by_id]
    accepted = {d: next(a for a in by_doc[d] if a["ok"]) for d in docs if any(a["ok"] for a in by_doc[d])}
    first_pass = sum(1 for d in docs if by_doc[d][0]["ok"])
    used = [next((a["attempt"] for a in by_doc[d] if a["ok"]), max_attempts) for d in docs]
    histogram: Counter[str] = Counter()
    for d in docs:
        for a in by_doc[d]:
            if a.get("api_failure"):
                continue  # API-level E1 is reported separately, never as a validator failure
            for reason in a["reasons"]:
                match = re.match(r"(V\d+[bp]?(?:/V\d+)?|API error|E1)", reason)
                histogram[match.group(1) if match else "other"] += 1
    calls = [a for d in docs for a in by_doc[d] if not a["cached"]]
    total_cost = sum(a["usd"] for d in docs for a in by_doc[d]) + sum(
        e.get("usd", 0.0) for e in events
    )
    ratios, within = [], 0
    bigrams: list[tuple[str, str]] = []
    openings: list[tuple[str, ...]] = []
    flags = []
    for d, a in accepted.items():
        words = [w.lower() for w in WORD_RE.findall(a["text"])]
        target = row_by_id[d]["target_words"]
        ratio = len(words) / target
        ratios.append(ratio)
        within += abs(ratio - 1) <= 0.15
        bigrams += list(zip(words, words[1:]))
        openings.append(tuple(words[:5]))
        flags.append(len(flagged_capitals(a["text"], row_by_id[d], kb)))
    n_docs = max(1, len(docs))
    n_acc = len(accepted)
    cost_per_accepted = total_cost / n_acc if n_acc else float("inf")
    metrics = {
        "model": model,
        "docs": len(docs),
        "first_attempt_pass": first_pass / n_docs,
        "accepted_within_3": n_acc / n_docs,
        "mean_attempts": _mean([float(u) for u in used]),
        "reason_histogram": dict(sorted(histogram.items())),
        "mean_input_tokens": _mean([a["input_tokens"] for a in calls]),
        "mean_output_tokens": _mean([a["output_tokens"] for a in calls]),
        "mean_reasoning_tokens": _mean([a["reasoning_tokens"] for a in calls]),
        "total_cost": total_cost,
        "cost_per_accepted": cost_per_accepted,
        "projected_full_run": cost_per_accepted * FULL_RUN_DOCS,
        "mean_length_ratio": _mean(ratios),
        "within_15pct": within / n_acc if n_acc else 0.0,
        "mean_latency": _mean([a["latency"] for a in calls]),
        "distinct_2gram": len(set(bigrams)) / len(bigrams) if bigrams else 0.0,
        "opening_5gram_dup": 1 - len(set(openings)) / len(openings) if openings else 1.0,
        "mean_capital_flags": _mean([float(f) for f in flags]),
    }
    all_attempts = [a for d in docs for a in by_doc[d]]

    def mode_of(row: dict[str, Any]) -> str:
        modes = set(row["modes"])
        return "none" if not modes else (modes.pop() if len(modes) == 1 else "mixed")

    def pass_by(key) -> dict[str, tuple[int, int]]:
        out: dict[str, list[int]] = {}
        for d in docs:
            bucket = out.setdefault(key(row_by_id[d]), [0, 0])
            bucket[1] += 1
            bucket[0] += bool(by_doc[d][0]["ok"])
        return {k: (v[0], v[1]) for k, v in sorted(out.items())}

    per_attempt_cost = total_cost / max(1, len(all_attempts))
    metrics.update(
        {
            "first_pass_by_mode": pass_by(mode_of),
            "first_pass_by_type": pass_by(lambda r: r["doc_type"]),
            "empty_responses": sum(1 for a in all_attempts if not a["text"].strip()) + len(events),
            "e1_events": len(events),
            "e1_failed_docs": sum(1 for d in docs if by_doc[d][-1].get("api_failure")),
            "attempts_made": len(all_attempts),
            "cost_per_doc": total_cost / n_docs,
            "projected_at_observed_attempts": total_cost / n_docs * FULL_RUN_DOCS,
            "projected_at_1_4_attempts": per_attempt_cost * 1.4 * FULL_RUN_DOCS,
        }
    )
    metrics["criteria"] = {
        "C1": metrics["accepted_within_3"] >= C_THRESHOLDS["C1"],
        "C2": metrics["first_attempt_pass"] >= C_THRESHOLDS["C2"],
        "C3": metrics["projected_full_run"] <= C_THRESHOLDS["C3"],
        "C4": metrics["within_15pct"] >= C_THRESHOLDS["C4"],
        "C5": metrics["opening_5gram_dup"] <= C_THRESHOLDS["C5"],
        "C6": None,
    }
    return metrics


def recommend(all_metrics: list[dict[str, Any]]) -> str:
    passing = [
        m for m in all_metrics if all(m["criteria"][c] for c in ("C1", "C2", "C3", "C4", "C5"))
    ]
    if passing:
        best = min(passing, key=lambda m: m["projected_full_run"])
        return (
            f"{best['model']} (cheapest model passing C1-C5, projected "
            f"${best['projected_full_run']:.2f}); final choice pending C6 human read-through."
        )
    if not any(m["criteria"]["C1"] or m["criteria"]["C2"] for m in all_metrics):
        return (
            "No model passes C1 or C2: iterate the prompt (template v3) using the reason "
            "histogram, within the remaining pilot budget."
        )
    return "No model passes C1-C5 together: see the failing criteria and iterate the prompt."


def extended_lines(all_metrics: list[dict[str, Any]]) -> list[str]:
    names = [m["model"] for m in all_metrics]
    lines = ["", "## Additional measures (prompt v3 / validator v2 rerun)", ""]
    header = "| measure | " + " | ".join(names) + " |"
    sep = "| --- | " + " | ".join("---:" for _ in names) + " |"

    def fmt(passed_total: tuple[int, int]) -> str:
        passed, total = passed_total
        return f"{passed}/{total} ({passed / total:.0%})" if total else "-"

    rows = [
        ("empty responses (expected 0)", lambda m: m["empty_responses"]),
        ("E1 API events (empty or length)", lambda m: m["e1_events"]),
        ("docs lost to E1 after retries", lambda m: m["e1_failed_docs"]),
        ("mean reasoning tokens / call (expected 0)", lambda m: f"{m['mean_reasoning_tokens']:.0f}"),
        ("attempts made", lambda m: m["attempts_made"]),
        ("mean attempts per doc", lambda m: f"{m['mean_attempts']:.2f}"),
        ("cost per doc (USD)", lambda m: f"${m['cost_per_doc']:.5f}"),
        ("projected full run at observed attempts/doc (USD)",
         lambda m: f"${m['projected_at_observed_attempts']:.2f}"),
        ("projected full run at 1.4 attempts/doc (USD)",
         lambda m: f"${m['projected_at_1_4_attempts']:.2f}"),
    ]
    lines += [header, sep]
    for label, fn in rows:
        lines.append("| " + " | ".join([label] + [str(fn(m)) for m in all_metrics]) + " |")
    lines += ["", "First-attempt pass by mode:", "", header, sep]
    for mode in sorted({k for m in all_metrics for k in m["first_pass_by_mode"]}):
        lines.append("| " + " | ".join([mode] + [fmt(m["first_pass_by_mode"].get(mode, (0, 0)))
                                                  for m in all_metrics]) + " |")
    lines += ["", "First-attempt pass by doc type:", "", header, sep]
    for kind in sorted({k for m in all_metrics for k in m["first_pass_by_type"]}):
        lines.append("| " + " | ".join([kind] + [fmt(m["first_pass_by_type"].get(kind, (0, 0)))
                                                  for m in all_metrics]) + " |")
    return lines


def write_report(
    path: Path,
    all_metrics: list[dict[str, Any]],
    spend: dict[str, float],
    client: str,
    extended: bool = False,
    template: tuple[str, str] | None = None,
    validator_version: str = "v1",
) -> None:
    def verdict(value: bool | None) -> str:
        return "pending human" if value is None else ("PASS" if value else "FAIL")

    lines = [
        f"Client: {client}",
        "",
        "# Pilot report",
        "",
        f"Template: {(template or (TEMPLATE_VERSION, template_hash()))[0]} "
        f"({(template or (TEMPLATE_VERSION, template_hash()))[1]}); validator {validator_version}. "
        "Generated "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        f"Global spend so far: ${spend['global']:.4f} of ${spend['global_cap']:.2f}; "
        f"pilot spend: ${spend['pilot']:.4f} of ${spend['pilot_cap']:.2f}.",
        "",
    ]
    header = ["metric"] + [m["model"] for m in all_metrics]
    rows = [
        ("docs", lambda m: m["docs"]),
        ("first-attempt pass rate", lambda m: f"{m['first_attempt_pass']:.1%}"),
        ("accepted within 3 attempts", lambda m: f"{m['accepted_within_3']:.1%}"),
        ("mean attempts per doc", lambda m: f"{m['mean_attempts']:.2f}"),
        ("mean input tokens / call", lambda m: f"{m['mean_input_tokens']:.0f}"),
        ("mean output tokens / call", lambda m: f"{m['mean_output_tokens']:.0f}"),
        ("mean reasoning tokens / call", lambda m: f"{m['mean_reasoning_tokens']:.0f}"),
        ("total cost (USD)", lambda m: f"${m['total_cost']:.4f}"),
        ("cost per accepted doc (USD)", lambda m: f"${m['cost_per_accepted']:.5f}"),
        ("projected full run, 2407 docs (USD)", lambda m: f"${m['projected_full_run']:.2f}"),
        ("mean actual/target words", lambda m: f"{m['mean_length_ratio']:.3f}"),
        ("docs within +/-15% of target", lambda m: f"{m['within_15pct']:.1%}"),
        ("mean latency (s)", lambda m: f"{m['mean_latency']:.2f}"),
        ("distinct-2gram ratio", lambda m: f"{m['distinct_2gram']:.3f}"),
        ("opening-5-gram duplicate rate", lambda m: f"{m['opening_5gram_dup']:.1%}"),
        ("mean capitalized-token flags / doc", lambda m: f"{m['mean_capital_flags']:.2f}"),
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in all_metrics) + " |")
    for label, fn in rows:
        lines.append("| " + " | ".join([label] + [str(fn(m)) for m in all_metrics]) + " |")
    lines += ["", "## Validator reason histogram (failed attempts, by rule)", ""]
    rules = sorted({r for m in all_metrics for r in m["reason_histogram"]})
    lines.append("| rule | " + " | ".join(m["model"] for m in all_metrics) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in all_metrics) + " |")
    for rule in rules or ["(none)"]:
        lines.append(
            f"| {rule} | " + " | ".join(str(m["reason_histogram"].get(rule, 0)) for m in all_metrics) + " |"
        )
    lines += ["", "## Selection criteria (docs/GENERATION_DECISION.md)", ""]
    names = {
        "C1": "accepted within 3 attempts >= 95%",
        "C2": "first-attempt pass >= 60%",
        "C3": "projected full-run cost <= $6.00",
        "C4": ">= 80% of accepted docs within +/-15% of target words",
        "C5": "opening-5-gram duplicate rate <= 10%",
        "C6": "human read-through of printed samples",
    }
    lines.append("| criterion | " + " | ".join(m["model"] for m in all_metrics) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in all_metrics) + " |")
    for key, label in names.items():
        lines.append(
            f"| {key}: {label} | "
            + " | ".join(verdict(m["criteria"][key]) for m in all_metrics)
            + " |"
        )
    if extended:
        lines += extended_lines(all_metrics)
    lines += ["", f"**Recommended model:** {recommend(all_metrics)}", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---- F. samples --------------------------------------------------------------------------

SAMPLE_KINDS: list[tuple[str, Any]] = [
    ("templated email", lambda r: r["pilot_category"] == "templated" and r["doc_type"] == "employee email"),
    ("paraphrased help-center article", lambda r: r["pilot_category"] == "paraphrased" and r["doc_type"] == "help-center article"),
    ("chat thread", lambda r: r["doc_type"] == "internal chat thread"),
    ("complaint letter + reply", lambda r: r["doc_type"] == "complaint letter + reply"),
    ("val-novel doc", lambda r: r["pilot_category"] == "val-novel"),
]


def write_samples(
    path: Path,
    rows: list[dict[str, Any]],
    attempts_by_model: dict[str, list[dict[str, Any]]],
    kb: dict[str, Any],
    pools: dict[str, Any],
    client: str,
    validator_version: str = "v2",
    extra: bool = False,
) -> None:
    validate = validator_for(validator_version)
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    lines = [
        f"Client: {client}",
        "",
        "# Pilot samples",
        "",
        "Accepted documents per model, printed in full.",
        "",
    ]
    for model, attempts in attempts_by_model.items():
        lines += [f"## {model}", ""]
        accepted = {a["doc_id"]: a for a in attempts if a["ok"]}
        taken: set[str] = set()
        kinds = list(SAMPLE_KINDS)
        if extra:
            kinds += [
                ("additional accepted email", lambda r: r["doc_type"] == "employee email"),
                ("additional accepted complaint reply",
                 lambda r: r["doc_type"] == "complaint letter + reply"),
            ]
        for number, (label, predicate) in enumerate(kinds, start=1):
            row = next(
                (r for r in rows if predicate(r) and r["doc_id"] in accepted and r["doc_id"] not in taken),
                None,
            )
            lines.append(f"### Sample {number}: {label}")
            if row is None:
                lines += ["", "(no accepted document of this kind)", ""]
                continue
            taken.add(row["doc_id"])
            text = accepted[row["doc_id"]]["text"]
            ok, reasons = validate(text, row, kb, pools)
            assigned = [
                f"{facts[f]['entity']} = {facts[f]['value']} ({mode})"
                for f, mode in zip(row["fact_ids"], row["modes"])
            ] or ["none (background)"]
            lines += [
                "",
                f"- id: {row['doc_id']}",
                f"- doc type: {row['doc_type']}",
                f"- style: {style_sentence(row['style_card'])} Target about {row['target_words']} words.",
                f"- assigned facts: {'; '.join(assigned)}",
                "",
                "```text",
                text,
                "```",
                "",
                f"Validator verdict: {'PASS' if ok else 'FAIL ' + '; '.join(reasons)}",
                "",
            ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---- orchestration -----------------------------------------------------------------------


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def projected_worst_case(
    guard: GlobalBudgetGuard,
    models: list[str],
    rows: list[dict[str, Any]],
    kb: dict[str, Any],
    max_attempts: int,
    max_output_tokens: int,
    builder=None,
) -> float:
    builder = builder or build_prompt
    total = 0.0
    for model in models:
        for row in rows:
            total += max_attempts * guard.cost(
                model, len(builder(row, kb)) // 4, max_output_tokens
            )
    return total


def run_pilot(
    backend: Backend,
    models: list[str],
    n: int,
    out_dir: Path,
    data_dir: Path,
    reports_dir: Path,
    notes_path: Path,
    client_name: str,
    echo=print,
    overwrite: bool = False,
    *,
    suffix: str = "",
    rows_from: Path | None = None,
    prompt_version: str = "v2",
    validator_version: str = "v2",
    use_saved_api_config: bool = False,
    extra_pilot_ledgers: list[Path] | None = None,
    session_cap: float | None = None,
    extended: bool = False,
) -> int:
    """Full pilot: A model check, B probe, C rows, D generate, E report, F samples."""
    backend.client_name = client_name  # type: ignore[attr-defined]
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    kb = load_json(ROOT / "data" / "kb" / "kb.json")
    pools = load_json(ROOT / "data" / "kb" / "filler_pools.json")
    plan_rows = [
        json.loads(x)
        for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    guard = GlobalBudgetGuard(
        data_dir, out_dir / "ledger.jsonl", config["budget_usd"], config["pilot_budget_usd"],
        {m: config["models"][m] for m in config["models"]},
        extra_pilot_ledgers=extra_pilot_ledgers, session_cap_usd=session_cap,
    )
    tools = prompt_tools(prompt_version)
    echo(mode_banner(client_name, guard.global_spent(), guard.global_cap_usd))
    echo(f"Global spend: ${guard.global_spent():.4f} / ${guard.global_cap_usd:.2f}; "
         f"pilot spend: ${guard.pilot_spent():.4f} / ${guard.pilot_cap_usd:.2f}")
    for name in (f"pilot_report{suffix}.md", f"pilot_samples{suffix}.md"):
        existing = reports_dir / name
        if existing.exists() and not overwrite:
            first = existing.read_text(encoding="utf-8").split("\n", 1)[0].strip()
            if first != f"Client: {client_name}":
                echo(f"Refusing to start: {existing} says '{first}', this run is "
                     f"'Client: {client_name}'. Use a different folder or pass --overwrite.")
                return 5
    unknown = [m for m in models if m not in config["models"]]
    if unknown:
        echo(f"No pricing in configs/generation.yaml for: {unknown}. Stopping.")
        return 2

    ok, missing, available = check_models(backend, models)
    if not ok:
        echo(f"Model ids not available for this key: {missing}")
        echo("Available ids starting with gpt-5: " + ", ".join(available))
        return 2

    if rows_from is not None:
        by_id = {r["doc_id"]: r for r in plan_rows}
        saved = [
            json.loads(x) for x in rows_from.read_text(encoding="utf-8").splitlines() if x.strip()
        ]
        rows = [{**by_id[r["doc_id"]], "pilot_category": r["pilot_category"]} for r in saved][:n]
    else:
        rows = select_pilot_rows(plan_rows, config["seed"], n)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot_rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    max_attempts = config["generation"]["max_attempts"]
    max_out = config["generation"]["max_output_tokens"]
    saved_config = load_json(out_dir / "api_config.json") if use_saved_api_config else {}
    model_max = {m: saved_config.get(m, {}).get("max_output_tokens", max_out) for m in models}
    worst = sum(
        projected_worst_case(guard, [m], rows, kb, max_attempts, model_max[m], tools["build"])
        for m in models
    )
    caps = [guard.global_cap_usd - guard.global_spent(), guard.pilot_cap_usd - guard.pilot_spent()]
    if session_cap is not None:
        caps.append(session_cap - guard.session_spent())
    remaining = min(caps)
    echo(f"Worst-case pilot cost ${worst:.4f}; remaining under tightest cap ${remaining:.4f}")
    if worst > remaining:
        echo("Refusing to start: the worst case would breach a spend cap. Lower --n.")
        return 3

    api_path = out_dir / "api_config.json"
    api_config = load_json(api_path) if api_path.exists() else {}
    if use_saved_api_config and any(not api_config.get(m, {}).get("config") for m in models):
        echo("Saved API configuration is missing; run scripts/preflight.py first.")
        return 4
    probes = {}
    for model in models:
        if model not in api_config or not api_config[model].get("config"):
            probes[model] = probe_model(backend, model, guard)
            api_config[model] = probes[model]
            api_path.write_text(json.dumps(api_config, indent=2), encoding="utf-8")
        if not api_config[model].get("config"):
            write_api_notes(notes_path, probes)
            echo(f"No working API configuration for {model}; see {notes_path}. Stopping.")
            return 4
    if probes:
        write_api_notes(notes_path, probes)

    attempts_by_model = {}
    all_metrics = []
    for model in models:
        result = generate_model(
            backend, model, api_config[model]["config"], rows, kb, pools, guard, out_dir,
            max_attempts, model_max[model], config["generation"]["pilot_concurrency"],
            prompt_version, validator_version,
        )
        echo(f"{model}: {result}")
        attempts = _load_attempts(out_dir / _safe(model) / "attempts.jsonl")
        events = _load_attempts(out_dir / _safe(model) / "api_events.jsonl")
        attempts_by_model[model] = attempts
        all_metrics.append(analyze_model(model, rows, attempts, kb, max_attempts, events))
    spend = {
        "global": guard.global_spent(), "global_cap": guard.global_cap_usd,
        "pilot": guard.pilot_spent(), "pilot_cap": guard.pilot_cap_usd,
    }
    write_report(
        reports_dir / f"pilot_report{suffix}.md", all_metrics, spend, client_name,
        extended=extended, template=(tools["label"], tools["hash"]),
        validator_version=validator_version,
    )
    write_samples(
        reports_dir / f"pilot_samples{suffix}.md", rows, attempts_by_model, kb, pools,
        client_name, validator_version, extra=extended,
    )
    echo(f"Global spend now ${spend['global']:.4f}; pilot ${spend['pilot']:.4f}")
    echo(f"Wrote {reports_dir / f'pilot_report{suffix}.md'} and "
         f"{reports_dir / f'pilot_samples{suffix}.md'}")
    return 0
