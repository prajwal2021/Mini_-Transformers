# REPORT BACK R10 (final consistency pass)

No retraining, no new evaluations. Nothing pushed. `.env` not read.

## a) Tests / lint / git
Full pytest: 737 passed, 0 failed, 0 skipped (10:47). `ruff check .`: all checks passed. Commits: see `git log` (R10 commits on top of `be7476f`).

## b) Ledger: now 5 lines (`reports/test_access_log.jsonl`)
1. probes (test split at every checkpoint incl. init), 2. QA evaluation (E0/E1/E2, base and SFT), 3. checkpoint samples, 4. post-hoc fixed 3-epoch SFT evaluation, 5. **demo-prompt overlap check** (new): purpose "demo prompt novelty check, read-only, no model evaluation"; files `data/eval/qa_test.jsonl` and `data/corpus/test.jsonl` with sha256; ts `2026-11-07T07:56:42+00:00` (the time of R09 commit `7c3cb15`, as asked); git `dbd9529`, dirty = true (the state at the run: HEAD was `dbd9529` and the demo script was uncommitted); a `note` field says the line was entered retroactively in R10 and that only counts were printed.
Wording updated: `README.md` (5 entries, listed), `docs/DESIGN_CHANGES_v1.3.md` row 59, `docs/PROFESSOR_NOTES.md` note 8, `reports/integration/REPORT_BACK_R09.md` line 3 (it had said "no new test reads"; now corrected in place), the report's appendix A (one new limitation sentence: five lines; the fourth recorded git dirty = true because the taxonomy relabelling was uncommitted when it ran; results unaffected; the PDF is still 7 pages). Older report-back files (R00-R08) describe earlier states and are left as written. `DATA_CARD.md`, the report text and the bundle docs had no statement of a ledger count; the bundle now ships the ledger itself (`results/test_access_log.jsonl`).

## c) Branches, tag, push commands
- `main` was an ancestor of `integration` (main at `cd17f63`, integration 36 commits ahead and 0 behind), so the update is a **clean fast-forward**; nothing was resolved by hand. The four stream branches (`analysis-stream`, `eval-stream`, `model-stream`, `spec-stream`) are all ancestors of `integration`, so nothing outside `integration` is left out. The main checkout had one untracked directory (`data/pilot_mock_v6/`) that does not exist in `integration`, so it does not block the fast-forward.
- Done: `git -C ../NNP merge --ff-only integration` (main = integration HEAD), tag `v1.0-submission` on that commit. See the chat for the final hash and `git status`.
- `.gitignore` check: `.env`, `.env.local` (any `.env.*` except `.env.example`), `*.zip`, `/bundle/`, `/bundle.zip`, `*.pt`, `runs/real/` are all ignored (tested with `git check-ignore`); the only tracked `.env`-like file is `.env.example` (empty value). Nothing zip-like or model-weight-like is tracked.
- Push commands (the remote `origin` is `https://github.com/prajwal2021/Mini_-Transformers.git`; check that this repository is private before pushing):

      git push origin main
      git push origin integration
      git push origin v1.0-submission

  If you want a single submission branch on the remote, push only `main` and the tag; `integration` and `main` point to the same commit.

## d) Bundle and fresh clone
- Rebuilt (`python scripts/make_bundle.py --release --out bundle`): 49 files, 147.1 MiB (`bundle.zip` 133.2 MiB). It now holds the final report PDF (7 pages, with the new sentence), `docs/` (DESIGN, PREREG, DESIGN_CHANGES, DATA_CARD, ERROR_TAXONOMY, the three statements, the demo transcript and shot list) and the ledger. `--verify bundle`: **MANIFEST OK**. No key pattern in the bundle.
- Fresh-clone test (`scripts/fresh_clone_readme.py`, clean venv, CPU torch 2.11.0+cpu, committed HEAD `26dfa4b`): **PASS**. Six README commands 1.9 to 3.1 s each; `pip install -r bundle/requirements.txt` 129.8 s; package install 182.2 s; table reproduction 31.0 s (REPRODUCED); total 373 s. Report: `reports/integration/r10_fresh_clone_report.json`.

## e) Unfinished
- `docs/AI_USE_STATEMENT.md`: "What I personally verified" is an explicit placeholder for you; the statement says it should not be submitted with it unfilled.
- The AI statement states Claude's role (architect and reviewer, caught the E\* selection leak and the evidence path for the sign bug) as you described it; I cannot verify that from the repository.
- Pushing is yours. `bundle.zip` is not in git and must be submitted separately.
