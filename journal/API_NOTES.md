# API notes

Parameter probe results from `scripts/run_pilot.py` are appended here, with provider error
messages verbatim. No probe has been run yet (P02b tooling only).

## Probe 2026-11-02 20:35 UTC

### gpt-5.4-nano

Working configuration: `{"api": "chat", "reasoning_effort": "low"}`

- `{"api": "chat", "reasoning_effort": "minimal"}` -> FAILED: BadRequestError: Error code: 400 - Unsupported value: 'reasoning_effort' does not support 'minimal' with this model. Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'.
- `{"api": "chat", "reasoning_effort": "low"}` -> ok

### gpt-5.4-mini

Working configuration: `{"api": "chat", "reasoning_effort": "low"}`

- `{"api": "chat", "reasoning_effort": "minimal"}` -> FAILED: BadRequestError: Error code: 400 - Unsupported value: 'reasoning_effort' does not support 'minimal' with this model. Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'.
- `{"api": "chat", "reasoning_effort": "low"}` -> ok


## Preflight 2026-11-02 21:01 UTC (P02b4 stage 0)

- gpt-5.4-nano reasoning_effort=none: status=ok finish_reason=stop text='OK' usage: input=8 output=4 reasoning=0 cost=$0.000007
- gpt-5.4-mini reasoning_effort=none: status=ok finish_reason=stop text='OK' usage: input=8 output=4 reasoning=0 cost=$0.000024
