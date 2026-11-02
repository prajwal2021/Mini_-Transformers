# End-of-prompt workflow

## Division of labor (updated P02b2, D-033)

- The executor is Claude Code in VS Code with a full local shell.
- The AGENT runs tests, lint, smoke runs and the paid pilot when a prompt says so; makes LOCAL git
  commits at the end of each prompt (`git add -A`, then `git commit`); and owns all tracking and
  journal updates.
- The agent NEVER pushes. Before every commit it runs `git status` and aborts the commit if `.env`
  or any key-like file is staged.
- The HUMAN owns environment and pip installs, reviews each commit, and pushes. The human and the
  reviewer make model-selection and phase-completion decisions from the recorded evidence.
- Secret handling: the agent never prints, logs, echoes or reads the contents of `.env` or
  `OPENAI_API_KEY`. Scripts load the key internally; the agent only checks that it is present
  ("key present: yes/no").
- The agent always invokes Python as `.venv\Scripts\python.exe`, never bare `python`, and never runs
  pip install. If a dependency is missing, it stops and lists it in the report.
- Every prompt's first action is saving the prompt verbatim to `journal/prompts/Pxx.md`.

Every prompt follows this protocol:

1. Run tests and lint with `.venv\Scripts\python.exe -m pytest -q` and `.venv\Scripts\python.exe -m ruff check .`.
2. Update `track.txt`: checklist, prompt log, key numbers, and next step.
3. Append an entry to `journal/JOURNAL.md`.
4. Add D/E/F records if any.
5. Append the tool and human-verification record to `AI_USE.md`.
6. Make the local commit (never push) with the prompt's commit message.
7. Print the `REPORT BACK` block.

A phase is marked complete only when its documented exit criteria pass with recorded evidence.
