# AI use statement

I used AI tools heavily in this project. This page says which tools did what, based on the project's own log (`AI_USE.md`, `journal/`, git history).

**Claude (Anthropic), in a chat session: architect and reviewer.** Claude helped write the design document and the pre-registration, wrote the task prompts
that drove each stage, and reviewed every stage's report-back. Its review caught problems in the analysis plan, including a leak in how the training length
(E\*) was selected, and the evidence path that exposed the sign bug in the H1/H2 analysis (it asked for the audit that found it).

**Claude Code (Anthropic coding agent in VS Code; Claude Sonnet 5.5 in the later commits): implementer and runner.** Claude Code wrote most of the code in this
repository (model, training loop, probes, SFT, evaluation, analysis, report builder, release bundle, tests), ran the experiments on my machine (sweep, three
seeds, probes, SFT, QA evaluation), ran the audits, fixed the bugs found, and wrote the journals, report-back files and the draft report text. Most local commits
carry its co-author line.

**OpenAI Codex CLI: early scaffolding.** The first stages (project scaffold, knowledge base, validator, sizing, early pilots; October 2026) were done
with Codex CLI, as `AI_USE.md` records.

**OpenAI models called through the API: data generation.** `gpt-5.4-mini` generated the corpus documents and the sentence bank and judged the bank (the corpus,
bank and judge scripts in this repository); `gpt-5.4-nano` was used in the early pilot runs. The knowledge base itself (the 120 facts) was built by
deterministic code, not by a model.

**What the AI did and what I did.** The AI proposed and wrote the code, text and analyses; I set the research question and the constraints (the pre-registered
hypotheses, stop rules, the rule never to touch test data outside the logged path), chose between the options the AI presented, and decided what to accept. The
H1/H2 sign bug was found after the results were seen, through an audit I commissioned; the fix and its before/after numbers are disclosed in the report appendix.

**What I personally verified.**

> *[PLACEHOLDER: to be filled in by the student. List only what you actually checked yourself, for example which results you reproduced, which outputs you
> read, which claims you tested. This file does not claim any personal verification, and it should not be submitted with this placeholder still in it.]*

**Limits of this statement.** I cannot vouch for every line of AI-written code. The repository has an automated test suite and the analysis is reproducible from
the release bundle (`python scripts/reproduce_tables.py --bundle bundle`), but passing tests is not the same as my own review.
