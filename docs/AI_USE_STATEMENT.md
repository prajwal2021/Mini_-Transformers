# AI use statement

I used AI tools heavily in this project. This page says which tools did what, based on the project's own log (`AI_USE.md`, `journal/`, git history).

**Claude (Anthropic chat assistant): design, review and planning.** Claude helped write the design document and the pre-registration, reviewed each stage's
report-back, and planned the implementation tasks (what to build next, what to check, which stop conditions to use).

**Claude Code (Anthropic coding agent, Claude Sonnet 5.5 in the later commits): implementation and runs.** Claude Code wrote most of the code in this
repository (model, training loop, probes, SFT, evaluation, analysis, report builder, release bundle, tests), ran the experiments on my machine
(sweep, three seeds, probes, SFT, QA evaluation), and wrote the journals, report-back files and the draft report text. Most local commits carry its co-author line.

**OpenAI Codex CLI: early scaffolding.** The first stages (project scaffold, knowledge base, validator, sizing, early pilots; October 2026) were done
with Codex CLI, as `AI_USE.md` records.

**OpenAI models called through the API: data generation.** The training corpus (the documents), the sentence bank behind the fact sentences, and
the checks on the bank were generated or judged by OpenAI models: `gpt-5.4-mini` for the corpus, bank and judge scripts in this repository, and `gpt-5.4-nano`
in the early pilot runs. The knowledge base itself (the 120 facts) was built by deterministic code, not by a model.

**What the AI did and what I did.** The AI proposed and wrote the code, text and analyses; I set the research question and the constraints (the
pre-registered hypotheses, stop rules, the rule never to touch test data outside the logged path), chose between the options the AI presented, and
decided what to accept. The AI found and fixed bugs, including a sign bug in the H1/H2 analysis that I only learned about after seeing results; that fix and its
before/after numbers are disclosed in the report appendix.

**What I personally verified.**

> *[To be filled in by the student. Do not leave this section as is: list only what you actually checked yourself, for example which results you reproduced,
> which outputs you read, which claims you tested. This file does not claim any personal verification.]*

**Limits of this statement.** I cannot vouch for every line of AI-written code. The repository has an automated test suite and the analysis is reproducible from
the release bundle (`python scripts/reproduce_tables.py --bundle bundle`), but passing tests is not the same as my own review.
