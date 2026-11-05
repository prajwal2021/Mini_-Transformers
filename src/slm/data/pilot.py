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
    bank_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate every row for one model with validator feedback; resume from attempts.jsonl.

    A response with empty text or finish_reason "length" is an API-level E1 event: it is retried
    up to ``e1_extra_tries`` more times with the ORIGINAL prompt (no validator feedback), logged
    separately in api_events.jsonl, and never counted as a validator failure. Each stored attempt
    carries the raw and normalised text and the prompt and validator versions.
    """
    tools = prompt_tools(prompt_version, model, bank_dir)
    validate = validator_for(validator_version)
    normalise = normaliser_for(validator_version)
    model_dir = out_dir / _safe(model)
    cache_dir = model_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = model_dir / "attempts.jsonl"
    events_path = model_dir / "api_events.jsonl"
    done = _load_attempts(attempts_path)
    finished = {a["doc_id"] for a in done if a["ok"] or a["attempt"] >= max_attempts
                or a.get("api_failure") or a.get("stuck")}
    client_name = getattr(backend, "client_name", "openai")
    write_lock = threading.Lock()
    stop = {"error": None}
    versions = {"prompt_version": prompt_version, "validator_version": validator_version}

    def append(path: Path, record: dict[str, Any]) -> None:
        with write_lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def one(row: dict[str, Any]) -> None:
        feedback = ""
        previous_rules: frozenset[str] | None = None
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
            rule_set = frozenset(
                m.group(0) for r in reasons if (m := re.match(r"V\d+[bp]?", r))
            )
            # stuck rule (P02b7): two consecutive attempts failing with the identical rule set
            stuck = bool(not ok and rule_set and rule_set == previous_rules)
            previous_rules = rule_set
            append(attempts_path, {
                **base_record, "ok": ok, "reasons": reasons, "text": processed["text"],
                "raw_text": result.text, "ask_words": processed["ask_words"],
                "insertion_mode": processed["insertion_mode"],
                "insertion_modes": processed["insertion_modes"],
                "placements": processed.get("placements", {}),
                "stuck": stuck,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_tokens": result.reasoning_tokens, "latency": result.latency,
                "usd": usd, "cached": cached, "finish_reason": result.finish_reason,
            })
            if ok or stuck:
                return
            feedback = tools["feedback"](
                reasons, previous=processed["normalised_text"], row=row, kb=kb
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
    first_ok = {d: next(a["attempt"] for a in by_doc[d] if a["ok"]) for d in accepted}
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
        "accepted_within_3": sum(1 for n in first_ok.values() if n <= 3) / n_docs,
        "accepted_within_5": sum(1 for n in first_ok.values() if n <= 5) / n_docs,
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
            "accept_by_type": {
                t: (sum(1 for d in accepted if row_by_id[d]["doc_type"] == t),
                    sum(1 for d in docs if row_by_id[d]["doc_type"] == t))
                for t in sorted({row_by_id[d]["doc_type"] for d in docs})
            },
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
            "No model passes C1 or C2 under the original criteria; see the reason histogram."
        )
    return "No model passes C1-C5 together: see the failing criteria and iterate the prompt."


def extended_lines(all_metrics: list[dict[str, Any]]) -> list[str]:
    names = [m["model"] for m in all_metrics]
    lines = ["", "## Additional measures", ""]
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


A1_COST_LIMIT = 7.00


def a1_eligibility(m: dict[str, Any]) -> dict[str, Any]:
    """Amendment A1 criteria a-d for one model on the cohort in ``m``."""
    by_type = m["accept_by_type"]
    rates = {t: a / n for t, (a, n) in by_type.items() if n}
    a_ok = (
        m["accepted_within_5"] >= 0.97
        and all(a >= 1 for a, n in by_type.values() if n)
        and min(rates.values()) >= 0.5
    )
    return {
        "a": a_ok, "b": m["first_attempt_pass"] >= 0.60,
        "c": m["projected_at_observed_attempts"] <= A1_COST_LIMIT,
        "d": m["opening_5gram_dup"] <= 0.10,
        "min_type_rate": min(rates.values()) if rates else 0.0,
        "types_without_accept": [t for t, (a, n) in by_type.items() if n and a == 0],
    }


def v5_lines(
    data: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    rows: list[dict[str, Any]],
    kb: dict[str, Any],
    max_attempts: int,
    note: str | None = None,
) -> tuple[list[str], list[str]]:
    """Sections of the v5 report; returns (lines, models eligible under A1)."""
    row_by_id = {r["doc_id"]: r for r in rows}
    metrics = {
        m: analyze_model(m, rows, attempts, kb, max_attempts, events)
        for m, (attempts, events) in data.items()
    }
    names = list(data)
    lines: list[str] = []
    if note:
        lines += ["", f"**{note}**"]
    lines += ["", "## C1 at 3 and at 5 attempts, other original criteria", "",
              "| model | accepted within 3 (C1) | accepted within 5 | first-attempt pass (C2) | "
              "projected full run (C3, $6.00) | within +/-15% (C4) | opening-5-gram dup (C5) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for m in names:
        x, c = metrics[m], metrics[m]["criteria"]
        verdict = lambda ok: "PASS" if ok else "FAIL"  # noqa: E731
        lines.append(
            f"| {m} | {x['accepted_within_3']:.1%} {verdict(c['C1'])} | {x['accepted_within_5']:.1%} | "
            f"{x['first_attempt_pass']:.1%} {verdict(c['C2'])} | "
            f"${x['projected_full_run']:.2f} {verdict(c['C3'])} | "
            f"{x['within_15pct']:.1%} {verdict(c['C4'])} | {x['opening_5gram_dup']:.1%} {verdict(c['C5'])} |"
        )
    types = sorted({r["doc_type"] for r in rows})
    lines += ["", "## Acceptance within 5 attempts by doc type", "",
              "| doc type | " + " | ".join(names) + " |", "| --- | " + " | ".join("---:" for _ in names) + " |"]
    for t in types:
        cells = []
        for m in names:
            a, n = metrics[m]["accept_by_type"].get(t, (0, 0))
            cells.append(f"{a}/{n} ({a / n:.0%})" if n else "-")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")

    elig = {m: a1_eligibility(metrics[m]) for m in names}
    lines += ["", "## Amendment A1 eligibility (docs/GENERATION_DECISION.md)", "",
              "| criterion | " + " | ".join(names) + " |", "| --- | " + " | ".join("---" for _ in names) + " |"]

    def cell(ok: bool, text: str) -> str:
        return f"{text} {'PASS' if ok else 'FAIL'}"

    lines.append("| (a) accepted within 5 >= 97%, every type >= 1, no type < 50% | " + " | ".join(
        cell(elig[m]["a"], f"{metrics[m]['accepted_within_5']:.1%}; lowest type {elig[m]['min_type_rate']:.0%}"
             + (f"; no accepted doc: {', '.join(elig[m]['types_without_accept'])}" if elig[m]["types_without_accept"] else ""))
        for m in names) + " |")
    lines.append("| (b) first-attempt pass >= 60% | " + " | ".join(
        cell(elig[m]["b"], f"{metrics[m]['first_attempt_pass']:.1%}") for m in names) + " |")
    lines.append(f"| (c) projected full run at observed attempts/doc <= ${A1_COST_LIMIT:.2f} | " + " | ".join(
        cell(elig[m]["c"], f"${metrics[m]['projected_at_observed_attempts']:.2f}") for m in names) + " |")
    lines.append("| (d) opening-5-gram duplicates <= 10% | " + " | ".join(
        cell(elig[m]["d"], f"{metrics[m]['opening_5gram_dup']:.1%}") for m in names) + " |")
    eligible = [m for m in names if all(elig[m][k] for k in "abcd")]
    lines.append("| eligible under A1 | " + " | ".join("YES" if m in eligible else "NO" for m in names) + " |")

    lines += ["", "## Mean actual/target words by doc type (all non-empty attempts)", "",
              "| doc type | " + " | ".join(names) + " |", "| --- | " + " | ".join("---:" for _ in names) + " |"]
    for t in types:
        cells = []
        for m in names:
            ratios = [len(WORD_RE.findall(a["text"])) / row_by_id[a["doc_id"]]["target_words"]
                      for a in data[m][0] if a["text"].strip() and a["doc_id"] in row_by_id
                      and row_by_id[a["doc_id"]]["doc_type"] == t]
            cells.append(f"{sum(ratios) / len(ratios):.3f} (n={len(ratios)})" if ratios else "-")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines.append("| all types | " + " | ".join(
        f"{metrics[m]['mean_length_ratio']:.3f} (accepted only)" for m in names) + " |")

    lines += ["", "## Validator reason lines (failed attempts)", "",
              "| rule | " + " | ".join(names) + " |", "| --- | " + " | ".join("---:" for _ in names) + " |"]
    for rule in ("V18", "V15", "V11", "V1p"):
        counts = []
        for m in names:
            total = 0
            for a in data[m][0]:
                if a.get("api_failure"):
                    continue
                total += sum(1 for r in a["reasons"] if re.match(rf"{rule}(?!\w)", r))
            counts.append(total)
        lines.append(f"| {rule} | " + " | ".join(str(c) for c in counts) + " |")

    lines += ["", "## Confound audit: fact sentences alone on their line, accepted documents", "",
              "| model | templated (code-inserted) | paraphrased (model-written) |", "| --- | --- | --- |"]
    for m in names:
        share = alone_on_line_share(data[m][0], row_by_id, kb)
        cells = [f"{a}/{b} ({a / b:.0%})" if b else "-" for a, b in (share["templated"], share["paraphrased"])]
        lines.append(f"| {m} | {cells[0]} | {cells[1]} |")
    return lines, eligible


def v6_lines(
    data: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    rows: list[dict[str, Any]],
    kb: dict[str, Any],
    max_attempts: int,
    bank_dir: Path | None,
    spent_other: float,
    bank_cost: float,
) -> list[str]:
    """Extra sections of the v6 report: placements, stuck docs, projected totals, manipulation check."""
    from .bank import BankStore, grams, jaccard, skeleton, starts_with_for_entity

    row_by_id = {r["doc_id"]: r for r in rows}
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    names = list(data)
    metrics = {m: analyze_model(m, rows, a, kb, max_attempts, e) for m, (a, e) in data.items()}
    store = BankStore.load(bank_dir)
    lines: list[str] = ["", "## Placement counts of the accepted documents (model / repaired_*)", ""]
    counts: dict[str, Counter[tuple[str, str]]] = {m: Counter() for m in names}
    for m in names:
        for a in data[m][0]:
            if not a["ok"] or a["doc_id"] not in row_by_id:
                continue
            row = row_by_id[a["doc_id"]]
            for fact_id, mode in zip(row["fact_ids"], row["modes"]):
                meta = (a.get("placements") or {}).get(fact_id)
                if meta:
                    counts[m][(mode, meta["placement"])] += 1
    kinds = sorted({k for m in names for k in counts[m]})
    lines += ["| mode | placement | " + " | ".join(names) + " |", "| --- | --- | " + " | ".join("---:" for _ in names) + " |"]
    lines += [f"| {mode} | {place} | " + " | ".join(str(counts[m][(mode, place)]) for m in names) + " |"
              for mode, place in kinds]
    lines += ["", "## Stuck documents (two consecutive attempts failed with the identical rule set)", ""]
    any_stuck = False
    for m in names:
        for a in data[m][0]:
            if a.get("stuck"):
                any_stuck = True
                rules = sorted({r.split()[0] for r in a["reasons"]})
                lines.append(f"- {m}: {a['doc_id']} stopped at attempt {a['attempt']} ({row_by_id[a['doc_id']]['doc_type']}); rules {', '.join(rules)}")
    if not any_stuck:
        lines.append("(none)")
    lines += ["", "## Projected totals against the global budget", "",
              "| model | spent before bank and pilot | bank | documents (full run) | total | limit |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for m in names:
        for label, docs in (("at observed attempts/doc", metrics[m]["projected_at_observed_attempts"]),
                            ("at 1.4 attempts/doc", metrics[m]["projected_at_1_4_attempts"])):
            lines.append(f"| {m} {label} | ${spent_other:.2f} | ${bank_cost:.2f} | ${docs:.2f} | "
                         f"${spent_other + bank_cost + docs:.2f} | $9.00 |")
    lines += ["", "## Manipulation check: paraphrase diversity of the inserted sentences (accepted documents)", "",
              "| model | inserted | distinct sentences | equal to canonical | starts 'For <entity>,' | "
              "distinct 3-token prefixes | mean pairwise skeleton Jaccard per fact (facts with 2+ uses) |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in names:
        inserted: list[tuple[str, str, str]] = []
        for a in data[m][0]:
            if not a["ok"] or a["doc_id"] not in row_by_id:
                continue
            row = row_by_id[a["doc_id"]]
            for fact_id, mode in zip(row["fact_ids"], row["modes"]):
                meta = (a.get("placements") or {}).get(fact_id)
                if meta and mode == "paraphrased" and meta["sentence_id"] != "canonical":
                    inserted.append((fact_id, meta["sentence_id"], store.sentences[meta["sentence_id"]]["text"]))
        if not inserted:
            lines.append(f"| {m} | 0 | - | - | - | - | - |")
            continue
        texts = [t for _f, _i, t in inserted]
        canon = sum(t == facts[f]["canonical_sentence"] for f, _i, t in inserted)
        for_lead = sum(starts_with_for_entity(t, facts[f]["entity"]) for f, _i, t in inserted)
        prefixes = {" ".join(skeleton(t, facts[f]["entity"], facts[f]["value"]).split()[:3]) for f, _i, t in inserted}
        per_fact: dict[str, list[frozenset]] = {}
        for f, _i, t in inserted:
            per_fact.setdefault(f, []).append(grams(skeleton(t, facts[f]["entity"], facts[f]["value"])))
        pairs = [jaccard(x, y) for gs in per_fact.values() if len(gs) > 1
                 for i, x in enumerate(gs) for y in gs[i + 1:]]
        lines.append(
            f"| {m} | {len(inserted)} | {len(set(texts))}/{len(texts)} | {canon} | {for_lead} | "
            f"{len(prefixes)} | " + (f"{sum(pairs) / len(pairs):.3f} ({len(pairs)} pairs)" if pairs else "-") + " |")
    return lines


def a1_recommendation(eligible: list[str], aborted: bool, samples: str = "pilot_samples_v5.md") -> str:
    prefix = "The run stopped early (see the note above). " if aborted else ""
    if not eligible:
        return prefix + "Neither model is eligible under A1; stop and report. No model is named."
    return (
        prefix + f"Eligible under A1: {', '.join(eligible)}. Among eligible models the choice is by C6 "
        "(naturalness, no prompt or meta language; read " + samples + ") and then by cost; "
        "no model is chosen here."
    )


COHORTS = [("combined 50", None), ("same 30", "same30"), ("fresh 20", "fresh20")]


def alone_on_line_share(
    attempts: list[dict[str, Any]], rows: dict[str, dict[str, Any]], kb: dict[str, Any]
) -> dict[str, tuple[int, int]]:
    """Confound audit: per mode, fact sentences that sit alone on their line (accepted docs)."""
    from .doc_validator import sentence_list, strip_label

    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    out: dict[str, list[int]] = {"templated": [0, 0], "paraphrased": [0, 0]}
    for attempt in attempts:
        if not attempt["ok"]:
            continue
        row = rows[attempt["doc_id"]]
        text = attempt["text"]
        sentences = sentence_list(text)
        lines = [strip_label(line.strip()) for line in text.split("\n")]
        for fact_id, mode in zip(row["fact_ids"], row["modes"]):
            value = facts[fact_id]["value"]
            holder = next((x for x in sentences if value in x), None)
            if holder is None:
                continue
            out[mode][1] += 1
            out[mode][0] += any(line == holder for line in lines)
    return {k: (v[0], v[1]) for k, v in out.items()}


def v4_lines(
    data: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    rows: list[dict[str, Any]],
    kb: dict[str, Any],
    max_attempts: int,
) -> list[str]:
    """Cohort criteria, length by type, rule counts and the confound audit for the v4 report."""
    row_by_id = {r["doc_id"]: r for r in rows}
    lines = ["", "## Criteria by cohort (same thresholds as GENERATION_DECISION.md)", "",
             "| model | cohort | docs | C1 accepted within 3 | C2 first-attempt pass | "
             "C3 projected full run | C4 within +/-15% | C5 opening-5-gram dup |",
             "| --- | --- | ---: | --- | --- | --- | --- | --- |"]

    def cell(value: str, passed: bool) -> str:
        return f"{value} {'PASS' if passed else 'FAIL'}"

    for model, (attempts, events) in data.items():
        for label, cohort in COHORTS:
            ids = {r["doc_id"] for r in rows if cohort is None or r.get("cohort") == cohort}
            sub_rows = [r for r in rows if r["doc_id"] in ids]
            m = analyze_model(
                model, sub_rows, [a for a in attempts if a["doc_id"] in ids], kb, max_attempts,
                [e for e in events if e["doc_id"] in ids],
            )
            c = m["criteria"]
            lines.append(
                f"| {model} | {label} | {m['docs']} | "
                f"{cell(format(m['accepted_within_3'], '.1%'), c['C1'])} | "
                f"{cell(format(m['first_attempt_pass'], '.1%'), c['C2'])} | "
                f"{cell('$' + format(m['projected_full_run'], '.2f'), c['C3'])} | "
                f"{cell(format(m['within_15pct'], '.1%'), c['C4'])} | "
                f"{cell(format(m['opening_5gram_dup'], '.1%'), c['C5'])} |"
            )
    lines += ["", "## Mean actual/target words by doc type (all non-empty attempts, after calibration)", ""]
    types = sorted({r["doc_type"] for r in rows})
    lines += ["| doc type | " + " | ".join(data) + " |", "| --- | " + " | ".join("---:" for _ in data) + " |"]
    for doc_type in types:
        cells = []
        for model, (attempts, _events) in data.items():
            ratios = [
                len(WORD_RE.findall(a["text"])) / row_by_id[a["doc_id"]]["target_words"]
                for a in attempts
                if a["text"].strip() and row_by_id[a["doc_id"]]["doc_type"] == doc_type
            ]
            cells.append(f"{sum(ratios) / len(ratios):.3f} (n={len(ratios)})" if ratios else "-")
        lines.append(f"| {doc_type} | " + " | ".join(cells) + " |")
    all_ratios = {
        model: [len(WORD_RE.findall(a["text"])) / row_by_id[a["doc_id"]]["target_words"]
                for a in attempts if a["text"].strip()]
        for model, (attempts, _e) in data.items()
    }
    lines.append("| all types | " + " | ".join(
        f"{sum(v) / len(v):.3f} (n={len(v)})" if v else "-" for v in all_ratios.values()) + " |")

    lines += ["", "## Validator reason lines for the new and fidelity rules (failed attempts)", ""]
    counts = {}
    for model, (attempts, _events) in data.items():
        counter: Counter[str] = Counter()
        for a in attempts:
            if a.get("api_failure"):
                continue
            for reason in a["reasons"]:
                match = re.match(r"(V\d+[bp]?)", reason)
                if match:
                    counter[match.group(1)] += 1
        counts[model] = counter
    lines += ["| rule | " + " | ".join(data) + " |", "| --- | " + " | ".join("---:" for _ in data) + " |"]
    for rule in ("V1p", "V17", "V15"):
        lines.append(f"| {rule} | " + " | ".join(str(counts[m][rule]) for m in data) + " |")

    lines += ["", "## Confound audit: fact sentences alone on their line, accepted documents", ""]
    lines += ["| model | templated (code-inserted) | paraphrased (model-written) |", "| --- | --- | --- |"]
    for model, (attempts, _events) in data.items():
        share = alone_on_line_share(attempts, row_by_id, kb)
        cells = [f"{a}/{b} ({a / b:.0%})" if b else "-" for a, b in (share["templated"], share["paraphrased"])]
        lines.append(f"| {model} | {cells[0]} | {cells[1]} |")
    return lines


def write_report(
    path: Path,
    all_metrics: list[dict[str, Any]],
    spend: dict[str, float],
    client: str,
    extended: bool = False,
    template: tuple[str, str] | None = None,
    validator_version: str = "v1",
    extra_lines: list[str] | None = None,
    recommendation: str | None = None,
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
    if extra_lines:
        lines += extra_lines
    lines += ["", f"**Recommendation:** {recommendation or recommend(all_metrics)}", ""]
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
    per_type: bool = False,
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
        if per_type:
            shown_types = {
                r["doc_type"] for label, pred in SAMPLE_KINDS for r in rows
                if pred(r) and r["doc_id"] in accepted
            }
            first_five = []
            for _label, pred in SAMPLE_KINDS:
                match = next((r for r in rows if pred(r) and r["doc_id"] in accepted), None)
                first_five.append(match["doc_type"] if match else None)
            shown_types = {t for t in first_five if t}
            kinds += [
                (f"accepted {t}", (lambda r, t=t: r["doc_type"] == t))
                for t in sorted({r["doc_type"] for r in rows} - shown_types)
            ]
        elif extra:
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
    cohort_report: bool = False,
    a1_report: bool = False,
    early_abort_after: int = 0,
    early_abort_below: float = 0.35,
    bank_dir: Path | None = None,
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
    tools = prompt_tools(prompt_version, None, bank_dir)
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
        rows = [
            {**by_id[r["doc_id"]], "pilot_category": r["pilot_category"],
             **({"cohort": r["cohort"]} if "cohort" in r else {})}
            for r in saved
        ][:n]
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
        projected_worst_case(
            guard, [m], rows, kb, max_attempts, model_max[m], prompt_tools(prompt_version, m, bank_dir)["build"]
        )
        for m in models
    )
    caps = [guard.global_cap_usd - guard.global_spent(), guard.pilot_cap_usd - guard.pilot_spent()]
    if session_cap is not None:
        caps.append(session_cap - guard.session_spent())
    remaining = min(caps)
    echo(f"Worst-case pilot cost ${worst:.4f}; remaining under tightest cap ${remaining:.4f}")
    if cohort_report or a1_report:
        # Expected-cost projection: 2 attempts per doc, output at the requested length. Every call
        # still reserves its own worst case, so a cap breach stops the run mid-way.
        expected = 0.0
        for model in models:
            model_tools = prompt_tools(prompt_version, model, bank_dir)
            for row in rows:
                ask = (
                    model_tools["ask_words"](row)
                    if model_tools.get("ask_words") else row["target_words"]
                )
                expected += 2 * guard.cost(
                    model, len(model_tools["build"](row, kb)) // 4,
                    min(model_max[model], round(ask * 1.35)),
                )
        echo(f"Expected pilot cost ${expected:.4f} (2 attempts per doc, output at the ask length)")
        if expected > remaining:
            echo("Refusing to start: the expected cost would breach a spend cap. Lower --n.")
            return 3
    elif worst > remaining:
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

    ordered = sorted(rows, key=lambda r: r["doc_id"])
    chunks = (
        [ordered[:early_abort_after], ordered[early_abort_after:]]
        if early_abort_after and len(ordered) > early_abort_after else [ordered]
    )
    aborted = False
    done_rows: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        for model in models:
            result = generate_model(
                backend, model, api_config[model]["config"], chunk, kb, pools, guard, out_dir,
                max_attempts, model_max[model], config["generation"]["pilot_concurrency"],
                prompt_version, validator_version, bank_dir=bank_dir,
            )
            echo(f"{model}: {result}")
        done_rows += chunk
        if index == 0 and len(chunks) > 1:
            ids = {r["doc_id"] for r in chunk}
            rates = {}
            for model in models:
                firsts = [a for a in _load_attempts(out_dir / _safe(model) / "attempts.jsonl")
                          if a["doc_id"] in ids and a["attempt"] == 1]
                rates[model] = sum(a["ok"] for a in firsts) / max(1, len(firsts))
            echo("First-attempt pass after the first "
                 f"{len(chunk)} docs: " + ", ".join(f"{m} {r:.1%}" for m, r in rates.items()))
            if all(r < early_abort_below for r in rates.values()):
                aborted = True
                echo(f"Early abort: both models are below {early_abort_below:.0%}; stopping.")
                break
    rows = done_rows
    attempts_by_model = {}
    all_metrics = []
    for model in models:
        attempts = _load_attempts(out_dir / _safe(model) / "attempts.jsonl")
        events = _load_attempts(out_dir / _safe(model) / "api_events.jsonl")
        attempts_by_model[model] = attempts
        all_metrics.append(analyze_model(model, rows, attempts, kb, max_attempts, events))
    spend = {
        "global": guard.global_spent(), "global_cap": guard.global_cap_usd,
        "pilot": guard.pilot_spent(), "pilot_cap": guard.pilot_cap_usd,
    }
    extra = None
    recommendation = None
    if a1_report:
        note = (f"EARLY ABORT after {len(rows)} docs: both models were below "
                f"{early_abort_below:.0%} first-attempt pass; the remaining documents were not run."
                if aborted else None)
        extra, eligible = v5_lines(
            {m: (attempts_by_model[m], _load_attempts(out_dir / _safe(m) / "api_events.jsonl"))
             for m in models},
            rows, kb, max_attempts, note,
        )
        samples_name = f"pilot_samples{suffix}.md"
        recommendation = a1_recommendation(eligible, aborted, samples_name)
        if prompt_version == "v6":
            bank_path = (bank_dir or ROOT / "data" / "bank") / "ledger.jsonl"
            bank_cost = sum(
                json.loads(x).get("usd", 0.0) for x in bank_path.read_text(encoding="utf-8").splitlines()
                if x.strip() and json.loads(x).get("client") != "mock"
            ) if bank_path.exists() else 0.0
            pilot_cost = sum(m["total_cost"] for m in all_metrics)
            extra += v6_lines(
                {m: (attempts_by_model[m], _load_attempts(out_dir / _safe(m) / "api_events.jsonl"))
                 for m in models},
                rows, kb, max_attempts, bank_dir,
                max(0.0, guard.global_spent() - bank_cost - pilot_cost), bank_cost,
            )
    elif cohort_report:
        extra = v4_lines(
            {m: (attempts_by_model[m], _load_attempts(out_dir / _safe(m) / "api_events.jsonl"))
             for m in models},
            rows, kb, max_attempts,
        )
    write_report(
        reports_dir / f"pilot_report{suffix}.md", all_metrics, spend, client_name,
        extended=extended, template=(tools["label"], tools["hash"]),
        validator_version=validator_version, extra_lines=extra, recommendation=recommendation,
    )
    write_samples(
        reports_dir / f"pilot_samples{suffix}.md", rows, attempts_by_model, kb, pools,
        client_name, validator_version, extra=extended, per_type=a1_report,
    )
    echo(f"Global spend now ${spend['global']:.4f}; pilot ${spend['pilot']:.4f}")
    echo(f"Wrote {reports_dir / f'pilot_report{suffix}.md'} and "
         f"{reports_dir / f'pilot_samples{suffix}.md'}")
    return 0
