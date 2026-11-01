# AI Use

| date | tool | purpose | what humans verified |
|---|---|---|---|
| 2026-10-31 | Claude (Anthropic) | Design | Design document and project requirements |
| 2026-10-31 | OpenAI Codex CLI | Implementation | Scaffold, utility APIs, tests, and generated files |
| 2026-10-31 | OpenAI Codex CLI | P00b verification and workflow correction | Human verified the environment boundary; Codex recorded the missing `.venv/bin/python` and did not install dependencies |
| 2026-10-31 | OpenAI Codex CLI | P00b CUDA verification and cross-platform hygiene | Codex added CUDA diagnostics, a skip-if-unavailable matmul test, D-011/D-012, and recorded `nvidia-smi` evidence; human must verify Python/Torch |
| 2026-10-31 | OpenAI Codex CLI | P00c verification and P00 exit criteria | Human provided the environment; Codex verified tests, Ruff, Torch/CUDA, device diagnostics, and CUDA matmul |
| 2026-10-31 | OpenAI Codex CLI | P01 KB, validator, cell assignment, sizing, and prereg draft | Humans verified the design requirements; Codex authored literal data, deterministic scripts, tests, and reports; no LLM API was called |
| 2026-10-31 | OpenAI Codex CLI | P01b realism, validation, filler pools, and sizing correction | Humans verified the v1.2 requirements; Codex implemented range-driven literals and evidence checks; no LLM API was called |
| 2026-10-31 | OpenAI Codex CLI | P01c KB precision, plausibility, canonical style, and filler-pool correction | Humans verified the P01c requirements; Codex reran validator, tests, assignment, and sizing; no LLM API was called |
| 2026-10-31 | OpenAI Codex CLI | P01d final KB quality and entity-balance pass | Humans verified the P01d requirements; Codex added per-entity gates, assignment objective, tests, and reports; no LLM API was called |
