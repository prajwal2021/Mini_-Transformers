# Running the paid pilot

The pilot makes real API calls and spends money (worst case about $0.51; capped at $1.00 for the
pilot and $10.00 across all ledgers). Run it from the repository root in PowerShell. Since P02b2
the agent may run it; a human can rerun it with the same commands.

## Run modes cannot be confused

- `--client` is required: `mock` or `openai`.
- The first line printed is the banner: `MODE: MOCK (no spend)` or
  `MODE: OPENAI (spends real money; global spend so far $X of $10)`.
- Mock outputs go only to `data\pilot_mock\` and `reports\tables\mock\`. Real outputs go to
  `data\pilot\` and `reports\tables\`.
- Both report files start with a header line `Client: mock` or `Client: openai`.
- A run refuses to start if a report already in its target folder carries the other client's
  header (or none), unless `--overwrite` is passed.

## 1. Set up the key

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env        # set the line OPENAI_API_KEY=<your key>, save, close
git status --short  # .env must NOT be listed (it is ignored); stop if it appears
```

## 2. Optional dry run (no spend)

```powershell
.\.venv\Scripts\python.exe scripts\run_pilot.py --client mock --models gpt-5.4-nano gpt-5.4-mini
```

## 3. Run the pilot

```powershell
.\.venv\Scripts\python.exe scripts\run_pilot.py --client openai --models gpt-5.4-nano gpt-5.4-mini --n 30 --i-understand-this-spends-money
```

The script first checks that both model ids exist for your key (it prints the available `gpt-5*`
ids and stops if not), probes the working API parameters, prints the global spend, and then
generates with validator rules V1-V14. It is safe to rerun: finished documents are skipped and
responses are cached. If it stops early, read `journal\API_NOTES.md` and the console output.

## 4. Results

- `reports\tables\pilot_report.md`
- `reports\tables\pilot_samples.md`
- `data\pilot\api_config.json` and `journal\API_NOTES.md` (probe results)

Model selection then follows `docs\GENERATION_DECISION.md`. Never commit `.env`.
