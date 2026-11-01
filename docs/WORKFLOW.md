# End-of-prompt workflow

## Division of labor

- HUMAN owns environment and pip installs, all Git commits, and long-running jobs such as LLM data generation and full training runs.
- CODEX owns code, tests, quick smoke runs, and all tracking/journal updates.
- Codex always invokes Python as `.venv\Scripts\python.exe`, never bare `python`, and never runs pip install. If a dependency is missing, Codex stops and lists it in the report.
- Every prompt's first action is saving the prompt verbatim to `journal/prompts/Pxx.md`.
- Every prompt ends by printing a suggested commit message; the human commits.

Every prompt follows this protocol:

1. Run tests and lint with `.venv\Scripts\python.exe -m pytest -q` and `.venv\Scripts\python.exe -m ruff check .`.
2. Update `track.txt`: checklist, prompt log, key numbers, and next step.
3. Append an entry to `journal/JOURNAL.md`.
4. Add D/E/F records if any.
5. Append the tool and human-verification record to `AI_USE.md`.
6. Print a suggested commit message; the human commits.
7. Print the `REPORT BACK` block.

A phase is marked complete only when its documented exit criteria pass with recorded evidence.
