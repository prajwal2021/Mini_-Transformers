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

