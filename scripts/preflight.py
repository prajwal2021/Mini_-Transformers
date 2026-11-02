"""Stage 0 preflight: one tiny real call per model with reasoning_effort "none".

Spends well under $0.01. If "none" is rejected for a model, that model falls back to
reasoning_effort "low" with a 2500-token output cap. Results go to
data/pilot_v3/api_config.json and journal/API_NOTES.md. The key is loaded internally, never printed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from slm.data.budget import GlobalBudgetGuard
from slm.data.pilot import ApiError, OpenAIBackend, load_api_key

ROOT = Path(__file__).resolve().parents[1]


def make_guard(config: dict, out_dir: Path) -> GlobalBudgetGuard:
    return GlobalBudgetGuard(
        ROOT / "data",
        out_dir / "ledger.jsonl",
        config["budget_usd"],
        config["pilot_budget_usd"],
        config["models"],
        extra_pilot_ledgers=[ROOT / "data" / "pilot" / "ledger.jsonl"],
        session_cap_usd=config["session_cap_usd"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["gpt-5.4-nano", "gpt-5.4-mini"])
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "pilot_v3")
    args = parser.parse_args(argv)
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    guard = make_guard(config, args.out_dir)
    print("MODE: OPENAI (spends real money; global spend so far "
          f"${guard.global_spent():.2f} of ${config['budget_usd']:.0f})")
    print(f"pilot spend so far ${guard.pilot_spent():.4f} of ${guard.pilot_cap_usd:.2f}; "
          f"session cap ${guard.session_cap_usd:.2f}")
    backend = OpenAIBackend(load_api_key())
    backend.client_name = "openai"  # type: ignore[attr-defined]
    result: dict[str, dict] = {}
    notes = [f"\n## Preflight {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
             "(P02b4 stage 0)\n"]
    for model in args.models:
        entry = None
        for effort, cap in (("none", 30), ("low", 2500)):
            cfg = {"api": "chat", "reasoning_effort": effort}
            reserved = guard.reserve(model, 5, cap)
            try:
                call = backend_call(backend, model, cfg, cap)
            except ApiError as exc:
                guard.settle(reserved, doc_id="preflight", model=model, client="openai", usd=0.0,
                             error=str(exc))
                line = f"{model} reasoning_effort={effort}: REJECTED: {exc}"
                print(line)
                notes.append(f"- {line}")
                continue
            usd = guard.cost(model, call.input_tokens, call.output_tokens)
            guard.settle(reserved, doc_id="preflight", attempt=0, model=model, client="openai",
                         tokens_in=call.input_tokens, tokens_out=call.output_tokens,
                         reasoning=call.reasoning_tokens, usd=usd, finish_reason=call.finish_reason)
            line = (f"{model} reasoning_effort={effort}: status=ok finish_reason={call.finish_reason} "
                    f"text={call.text!r} usage: input={call.input_tokens} output={call.output_tokens} "
                    f"reasoning={call.reasoning_tokens} cost=${usd:.6f}")
            print(line)
            notes.append(f"- {line}")
            entry = {"config": cfg, "max_output_tokens": 700 if effort == "none" else cap}
            if effort == "low":
                notes.append(f"  - fallback for {model}: reasoning_effort low, max_output_tokens 2500 "
                             "(higher cost per call than none; the cap covers hidden reasoning)")
            break
        if entry is None:
            print(f"No usable configuration for {model}.")
            return 4
        result[model] = entry
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "api_config.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (ROOT / "journal" / "API_NOTES.md").open("a", encoding="utf-8") as handle:
        handle.write("\n".join(notes) + "\n")
    print(f"preflight spend this session: ${guard.session_spent():.6f}")
    return 0


def backend_call(backend, model, cfg, cap):
    return backend.call(model, "Say OK", cfg, cap)


if __name__ == "__main__":
    raise SystemExit(main())
