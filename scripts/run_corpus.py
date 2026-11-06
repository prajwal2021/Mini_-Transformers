"""Full corpus generation (P02c): gated, resumable, with re-plan rounds and leakage regeneration.

Stages: main (round 0 over all plan rows with Gate A and rolling gates), replan (unaccepted docs get a
new opener, rounds 1-2), leak (val/test docs sharing a 13-gram with train and near-duplicate train docs
are regenerated, rounds 3-4), assemble (writes train/val/test.jsonl and the raw records). --stage all
runs them in order. A real run needs --client openai and the spend flag; the key is never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

from slm.data import corpus
from slm.data.artifacts import artifact_rate
from slm.data.budget import BudgetExceeded, GlobalBudgetGuard, mode_banner
from slm.data.pilot import (
    MockBackend,
    OpenAIBackend,
    _safe,
    analyze_model,
    generate_model,
    load_api_key,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL = corpus.MODEL
FIRST_CHUNK, CHUNK = 150, 100
# P02c3 amendments: the per-type check applies to types with >= TYPE_MIN_DOCS documents in the evaluated
# chunk; the artifact rate (artifacts.py) over mention-bearing documents must be <= 2%.
GATES = {"acc5": 0.95, "attempts": 1.4, "cost": 6.00, "dup": 0.05, "type": 0.90, "artifact": 0.02}
TYPE_MIN_DOCS = 20
FAIL_ROUNDS = (1, 2)
REDO_FIRST = 350  # P02c4: first documents (hashed order) whose unaccepted ones are re-run with prompt v9
LEAK_ROUNDS = (3, 4)


def evaluate(metrics: dict, ledger_spend: float) -> dict[str, bool]:
    types = metrics["accept_by_type"]
    return {
        "accepted_within_5": metrics["accepted_within_5"] >= GATES["acc5"],
        "mean_attempts": metrics["mean_attempts"] <= GATES["attempts"],
        "projected_cost": metrics["projected_full_run"] <= GATES["cost"],
        "opening_dup": metrics["opening_5gram_dup"] <= GATES["dup"],
        "every_type": all(a / n >= GATES["type"] for a, n in types.values() if n >= TYPE_MIN_DOCS),
        "artifact_rate": metrics.get("artifact_rate", 0.0) <= GATES["artifact"],
        "spend": ledger_spend < GATES["cost"],
    }


class Run:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.mock = args.client == "mock"
        self.out = args.out_dir or (ROOT / "data" / ("corpus_mock" if self.mock else "corpus"))
        self.raw = self.out / "raw"
        self.reports = ROOT / "reports" / "tables" / ("mock" if self.mock else "")
        self.config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
        self.kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
        self.pools = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
        plan = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
        plan = corpus.apply_plan_overrides(plan, self.out)
        self.plan = plan[: args.limit] if args.limit else plan
        self.plan_by_id = {r["doc_id"]: r for r in self.plan}
        self.bank_dir = args.bank_dir
        self.raw.mkdir(parents=True, exist_ok=True)
        api_path = self.raw / "api_config.json"
        if not api_path.exists():
            api_path.write_text((ROOT / "data" / "pilot_v6" / "api_config.json").read_text(encoding="utf-8"),
                                encoding="utf-8")
        saved = json.loads(api_path.read_text(encoding="utf-8"))[MODEL]
        self.api_cfg = saved["config"]
        self.max_out = saved.get("max_output_tokens", self.config["generation"]["max_output_tokens"])
        pricing = {m: self.config["models"][m] for m in self.config["models"]}
        self.guard = GlobalBudgetGuard(
            ROOT / "data", self.raw / "ledger.jsonl", args.global_cap, args.cap, pricing)
        inner = MockBackend(models=[MODEL]) if self.mock else OpenAIBackend(load_api_key())
        self.backend = corpus.RetryingBackend(inner)
        self.backend.client_name = args.client  # type: ignore[attr-defined]
        print(mode_banner(args.client, self.guard.global_spent(), self.guard.global_cap_usd))
        print(f"corpus run: ledger cap ${args.cap:.2f}, global stop ${args.global_cap:.2f}, "
              f"{len(self.plan)} plan rows, workers {args.workers}")

    # -- generation --------------------------------------------------------------------------
    def generate(self, number: int, rows: list[dict], attempts: int = 5) -> str | None:
        if number:
            rows = [{**r, "replan": number} for r in rows]
        out = corpus.round_dir(self.raw, number)
        result = generate_model(
            self.backend, MODEL, self.api_cfg, rows, self.kb, self.pools, self.guard, out, attempts, self.max_out,
            self.args.workers, "v9", "v5", bank_dir=self.bank_dir,
        )
        return result["stopped"]

    def attempts(self, number: int = 0) -> list[dict]:
        path = corpus.round_dir(self.raw, number) / _safe(MODEL) / "attempts.jsonl"
        from slm.data.pilot import _load_attempts

        return _load_attempts(path)

    def ledger_spend(self) -> float:
        total = 0.0
        path = self.raw / "ledger.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    if entry.get("client") != "mock":
                        total += entry.get("usd", 0.0)
        return total

    # -- stage main --------------------------------------------------------------------------
    def progress(self, line: str, header: bool = False) -> None:
        path = self.reports / "corpus_progress.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(f"Client: {self.args.client}\n\n# Corpus progress\n\n| docs done | accepted within 5 | mean attempts | "
                            "projected full run | opening 5-gram dup | lowest type (n>=20) | artifact rate | ledger spend | gates |\n"
                            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
                            "\nRule (P02c4): a document accepted after its re-plan counts as accepted in the rolling gates.\n\n",
                            encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def main_stage(self) -> int:
        order = sorted(self.plan, key=lambda r: hashlib.sha256(("p02c" + r["doc_id"]).encode()).hexdigest())
        chunks = [order[:FIRST_CHUNK]]
        chunks += [order[i : i + CHUNK] for i in range(FIRST_CHUNK, len(order), CHUNK)]
        done: list[dict] = []
        for index, chunk in enumerate(chunks):
            stopped = self.generate(0, chunk)
            done += chunk
            events_path = self.raw / _safe(MODEL) / "api_events.jsonl"
            from slm.data.pilot import _load_attempts

            metrics = analyze_model(MODEL, done, self.gate_attempts(done), self.kb, 5, _load_attempts(events_path))
            chunk_docs, _missing = corpus.final_docs(done, self.gate_rounds())
            metrics["artifact_rate"], bad, bearing = artifact_rate(chunk_docs)
            spend = self.ledger_spend()
            ok = evaluate(metrics, spend)
            lowest = min((a / n for a, n in metrics["accept_by_type"].values() if n >= TYPE_MIN_DOCS), default=1.0)
            failing = [k for k, v in ok.items() if not v]
            self.progress(
                f"| {len(done)} | {metrics['accepted_within_5']:.1%} | {metrics['mean_attempts']:.2f} | "
                f"${metrics['projected_full_run']:.2f} | {metrics['opening_5gram_dup']:.1%} | {lowest:.0%} | "
                f"{metrics['artifact_rate']:.1%} ({bad}/{bearing}) | ${spend:.2f} | {'PASS' if not failing else 'FAIL: ' + ', '.join(failing)}"
                f"{' (Gate A)' if index == 0 else ''} |")
            print(self.progress_text(len(done), metrics, spend, failing, index == 0))
            if index == 0:
                self.write_first150(done)
            if stopped:
                print(f"STOPPED by a cap: {stopped}")
                return 3
            if failing:
                print(f"GATE FAIL after {len(done)} docs: {', '.join(failing)}; stopping.")
                return 3
        return 0

    def gate_rounds(self) -> dict[int, list[dict]]:
        return {n: a for n, a in self.rounds().items() if n <= max(FAIL_ROUNDS)}

    def gate_attempts(self, done: list[dict]) -> list[dict]:
        """Attempts the rolling gates see (P02c4): round 0, plus the attempts of a document that was not
        accepted in round 0 but is accepted after its re-plan (rounds 1-2). Such a document counts as
        accepted; its re-plan attempts are numbered 5 so that it counts as the worst case of 'within 5'
        for the attempts statistic, and their cost is included."""
        rounds = self.gate_rounds()
        base = rounds.get(0, [])
        ok0 = {a["doc_id"] for a in base if a["ok"]}
        ids = {r["doc_id"] for r in done}
        extra = []
        for number in FAIL_ROUNDS:
            for a in rounds.get(number, []):
                if a["doc_id"] in ids and a["doc_id"] not in ok0:
                    extra.append({**a, "attempt": 5, "replan_round": number})
        accepted_replan = {a["doc_id"] for a in extra if a["ok"]}
        return base + [a for a in extra if a["doc_id"] in accepted_replan]

    @staticmethod
    def progress_text(n: int, m: dict, spend: float, failing: list[str], gate_a: bool) -> str:
        return (f"{'Gate A' if gate_a else 'rolling'} at {n} docs: accepted within 5 {m['accepted_within_5']:.1%}, "
                f"attempts {m['mean_attempts']:.2f}, projected ${m['projected_full_run']:.2f}, opening dup "
                f"{m['opening_5gram_dup']:.1%}, artifact rate {m.get('artifact_rate', 0.0):.1%}, spend ${spend:.2f} -> {'PASS' if not failing else 'FAIL ' + str(failing)}")

    def write_first150(self, done: list[dict]) -> None:
        path = self.reports / "corpus_samples_first150.md"
        if path.exists():
            return
        docs, _missing = corpus.final_docs(done, {0: self.attempts(0)})
        picks = corpus.sample_docs(docs)
        lines = [f"Client: {self.args.client}", "", "# 12 accepted documents from the first 150 (seeded; one per document type, then random)", ""]
        for d in picks:
            lines += [f"## {d['doc_id']} ({d['doc_type']}, {d['mode']}, {d['regime']})", "", "```text", d["text"], "```", ""]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    # -- stage replan ------------------------------------------------------------------------
    def rounds(self) -> dict[int, list[dict]]:
        return corpus.load_rounds(self.raw)

    def unaccepted(self) -> list[dict]:
        accepted = corpus.accepted_by_doc(self.rounds())
        return [r for r in self.plan if r["doc_id"] not in accepted]

    def redo_stage(self) -> int:
        """P02c4: re-run the unaccepted documents among the first REDO_FIRST (hashed order) with prompt v9 and a
        new opener (round 1, then round 2)."""
        order = sorted(self.plan, key=lambda r: hashlib.sha256(("p02c" + r["doc_id"]).encode()).hexdigest())
        first = {r["doc_id"] for r in order[:REDO_FIRST]}
        for number in FAIL_ROUNDS:
            todo = [r for r in self.unaccepted() if r["doc_id"] in first]
            if not todo:
                break
            print(f"redo round {number}: {len(todo)} docs {[r['doc_id'] for r in todo]}")
            stopped = self.generate(number, todo)
            if stopped:
                print(f"STOPPED by a cap: {stopped}")
                return 3
        left = [r["doc_id"] for r in self.unaccepted() if r["doc_id"] in first]
        print(f"unaccepted among the first {REDO_FIRST} after redo: {left}")
        return 0

    def replan_stage(self) -> int:
        for number in FAIL_ROUNDS:
            todo = self.unaccepted()
            if not todo:
                break
            print(f"re-plan round {number}: {len(todo)} docs ({', '.join(r['doc_id'] for r in todo[:10])}...)")
            stopped = self.generate(number, todo)
            if stopped:
                print(f"STOPPED by a cap: {stopped}")
                return 3
        left = self.unaccepted()
        heldout = [r["doc_id"] for r in left if r["split"] != "train"]
        print(f"unaccepted after re-planning: {len(left)} ({len(heldout)} val/test)")
        (self.out / "unaccepted.json").write_text(json.dumps([r["doc_id"] for r in left]), encoding="utf-8")
        if heldout:
            print(f"val/test docs cannot be completed: {heldout}; stopping.")
            return 4
        return 0

    # -- stage leak --------------------------------------------------------------------------
    def current_docs(self) -> list[dict]:
        docs, _ = corpus.final_docs(self.plan, self.rounds(), self.dropped())
        return docs

    def dropped(self) -> set[str]:
        path = self.out / "dropped.json"
        return {x["doc_id"] for x in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else set()

    def leak_stage(self) -> int:
        dropped: list[dict] = []
        for number in LEAK_ROUNDS:
            docs = self.current_docs()
            leaky = corpus.leakage(docs)
            near = corpus.train_near_duplicates(docs)
            redo = set(leaky) | {b for _a, b, _j in near}
            print(f"leak round {number}: {len(leaky)} val/test docs share 13-grams with train "
                  f"(total shared {sum(leaky.values())}), {len(near)} train near-duplicate pairs")
            if not redo:
                break
            stopped = self.generate(number, [self.plan_by_id[d] for d in sorted(redo)])
            if stopped:
                print(f"STOPPED by a cap: {stopped}")
                return 3
        docs = self.current_docs()
        leaky = corpus.leakage(docs)
        near = corpus.train_near_duplicates(docs)
        for _a, b, jac in near:
            dropped.append({"doc_id": b, "reason": f"train near-duplicate (13-gram Jaccard {jac:.2f}) after regeneration"})
        (self.out / "dropped.json").write_text(json.dumps(dropped, indent=1), encoding="utf-8")
        print(f"after regeneration: leaky val/test docs {len(leaky)}, near-duplicate train pairs {len(near)} "
              f"(dropped {len(dropped)})")
        return 5 if leaky else 0

    # -- stage assemble ----------------------------------------------------------------------
    def assemble(self) -> int:
        docs = self.current_docs()
        corpus.write_split_files(self.out, docs)
        rounds = self.rounds()
        with (self.raw / "records.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in self.plan:
                handle.write(json.dumps(corpus.record_for(row, rounds), ensure_ascii=False) + "\n")
        print(f"wrote {len(docs)} docs to {self.out}; ledger spend ${self.ledger_spend():.4f}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--stage", choices=["redo", "main", "replan", "leak", "assemble", "all"], default="all")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--bank-dir", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--cap", type=float, default=6.00)
    parser.add_argument("--global-cap", type=float, default=9.00)
    parser.add_argument("--limit", type=int, default=0, help="first N plan rows (tests)")
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args(argv)
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    run = Run(args)
    stages = ["redo", "main", "replan", "leak", "assemble"] if args.stage == "all" else [args.stage]
    for stage in stages:
        try:
            code = {"redo": run.redo_stage, "main": run.main_stage, "replan": run.replan_stage, "leak": run.leak_stage,
                    "assemble": run.assemble}[stage]()
        except BudgetExceeded as exc:
            print(f"STOPPED by a cap: {exc}")
            return 3
        if code:
            if stage != "assemble":
                run.assemble()
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
