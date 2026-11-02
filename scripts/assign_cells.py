"""Assign P01 frequency/diversity cells with a seeded Latin-square design."""

from __future__ import annotations

import copy
import itertools
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from scipy.stats import kruskal

try:
    from scripts.validate_kb import DEFAULT_PATH, validate
except ModuleNotFoundError:
    from validate_kb import DEFAULT_PATH, validate


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "experiment.yaml"
REPORT_PATH = ROOT / "reports" / "tables" / "cell_balance.md"


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _families(facts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        grouped[fact["family"]].append(fact)
    return grouped


def _family_totals(
    entities: list[str], attributes: list[str], family_cells: list[str], planned: dict[str, int]
) -> dict[str, int]:
    totals = {entity: 0 for entity in entities}
    for attr_index, _attribute_id in enumerate(attributes):
        for entity_index, entity in enumerate(entities):
            cell = family_cells[(entity_index + attr_index) % len(family_cells)]
            totals[entity] += planned[cell.split("_", 1)[0]]
    return totals


def _ratio(totals: dict[str, int]) -> float:
    return max(totals.values()) / min(totals.values())


def _best_family_permutation(
    entities: list[str], attributes: list[str], family_cells: list[str], planned: dict[str, int]
) -> tuple[list[str], float]:
    candidates = []
    for permutation in itertools.permutations(family_cells):
        totals = _family_totals(entities, attributes, list(permutation), planned)
        candidates.append((_ratio(totals), tuple(permutation), totals))
    best_ratio, best_permutation, _totals = min(candidates, key=lambda item: (item[0], item[1]))
    return list(best_permutation), best_ratio


def _assign_for_seed(
    kb: dict[str, Any], seed: int, config: dict[str, Any]
) -> tuple[dict[str, Any], float, float, float, float, dict[str, list[str]]] | None:
    candidate = copy.deepcopy(kb)
    facts = candidate["measured_facts"]
    cells = list(config["cells"])
    planned = config["planned_mentions"]
    by_key = {(fact["family"], fact["entity"], fact["attribute_id"]): fact for fact in facts}
    rng = random.Random(seed)
    family_permutations: dict[str, list[str]] = {}
    for family, family_facts in _families(facts).items():
        entities = sorted({fact["entity"] for fact in family_facts})
        attributes = sorted({fact["attribute_id"] for fact in family_facts})
        rng.shuffle(entities)
        family_cells = cells.copy()
        rng.shuffle(family_cells)
        family_cells, _family_ratio = _best_family_permutation(
            entities, attributes, family_cells, planned
        )
        family_permutations[family] = family_cells
        for attr_index, attribute_id in enumerate(attributes):
            for entity_index, entity in enumerate(entities):
                fact = by_key[(family, entity, attribute_id)]
                cell = family_cells[(entity_index + attr_index) % len(family_cells)]
                freq_bin, div_bin = cell.split("_", 1)
                fact.update(
                    {
                        "freq_bin": freq_bin,
                        "div_bin": div_bin,
                        "cell": cell,
                        "planned_mentions": planned[freq_bin],
                    }
                )
    by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        by_cell[fact["cell"]].append(fact)
    all_attributes = sorted({fact["attribute_id"] for fact in facts})
    for cell_index, cell in enumerate(cells):
        start = (seed + cell_index * 8) % len(all_attributes)
        train_attributes = {
            all_attributes[(start + offset) % len(all_attributes)] for offset in range(8)
        }
        val_attributes = {
            all_attributes[(start + 8 + offset) % len(all_attributes)] for offset in range(2)
        }
        for fact in by_cell[cell]:
            if fact["attribute_id"] in train_attributes:
                fact["sft_split"] = "sft_train"
            elif fact["attribute_id"] in val_attributes:
                fact["sft_split"] = "sft_val"
            else:
                fact["sft_split"] = "heldout"
    attr_splits: dict[str, Counter[str]] = defaultdict(Counter)
    for fact in facts:
        attr_splits[fact["attribute_id"]][fact["sft_split"]] += 1
    if any(counts["sft_train"] < 2 or counts["heldout"] < 2 for counts in attr_splits.values()):
        return None
    lengths_by_cell = [[fact["char_len"] for fact in by_cell[cell]] for cell in cells]
    global_mean = sum(fact["char_len"] for fact in facts) / len(facts)
    variance = sum((fact["char_len"] - global_mean) ** 2 for fact in facts) / len(facts)
    global_std = variance**0.5 or 1.0
    imbalance = max(
        abs(sum(values) / len(values) - global_mean) / global_std for values in lengths_by_cell
    )
    kw_p = float(kruskal(*lengths_by_cell).pvalue)
    if kw_p <= 0.2:
        return None
    family_totals = {
        family: {
            entity: sum(
                fact["planned_mentions"]
                for fact in facts
                if fact["family"] == family and fact["entity"] == entity
            )
            for entity in sorted({fact["entity"] for fact in facts if fact["family"] == family})
        }
        for family in sorted({fact["family"] for fact in facts})
    }
    entity_ratio = max(_ratio(totals) for totals in family_totals.values())
    objective = imbalance + 0.25 * (entity_ratio - 1)
    return candidate, imbalance, kw_p, entity_ratio, objective, family_permutations


def _write_report(
    kb: dict[str, Any], seed: int, imbalance: float, kw_p: float, entity_ratio: float, objective: float
) -> None:
    facts = kb["measured_facts"]
    cells = [
        "low_templated",
        "low_paraphrased",
        "mid_templated",
        "mid_paraphrased",
        "high_templated",
        "high_paraphrased",
    ]
    lines = [
        "# Cell balance",
        "",
        f"Chosen seed: **{seed}**",
        f"Covariate imbalance: `{imbalance:.4f}`",
        f"Entity ratio: `{entity_ratio:.4f}`",
        f"Selection objective: `{objective:.4f}`",
        f"Kruskal-Wallis p-value: `{kw_p:.4f}`",
        "Per-family cell permutations: "
        + "; ".join(
            f"{family}={','.join(permutation)}"
            for family, permutation in sorted(kb["assignment"]["family_permutations"].items())
        ),
        "",
    ]
    lines += [
        "## Cell x attribute counts",
        "",
        "| attribute | " + " | ".join(cells) + " |",
        "|---|" + "---|" * len(cells),
    ]
    for attribute in sorted({fact["attribute_id"] for fact in facts}):
        counts = Counter(fact["cell"] for fact in facts if fact["attribute_id"] == attribute)
        lines.append(
            "| " + attribute + " | " + " | ".join(str(counts[cell]) for cell in cells) + " |"
        )
    lines += [
        "",
        "## Cell x family counts",
        "",
        "| family | " + " | ".join(cells) + " |",
        "|---|" + "---|" * len(cells),
    ]
    for family in sorted({fact["family"] for fact in facts}):
        counts = Counter(fact["cell"] for fact in facts if fact["family"] == family)
        lines.append("| " + family + " | " + " | ".join(str(counts[cell]) for cell in cells) + " |")
    lines += [
        "",
        "## Cell x entity counts",
        "",
        "| family/entity | " + " | ".join(cells) + " |",
        "|---|" + "---|" * len(cells),
    ]
    for family, entity in sorted({(fact["family"], fact["entity"]) for fact in facts}):
        counts = Counter(
            fact["cell"] for fact in facts if fact["family"] == family and fact["entity"] == entity
        )
        lines.append(
            "| "
            + family
            + "/"
            + entity
            + " | "
            + " | ".join(str(counts[cell]) for cell in cells)
            + " |"
        )
    lines += [
        "",
        "## Per-entity total planned mentions",
        "",
        "| family/entity | total planned mentions | family ratio |",
        "|---|---:|---:|",
    ]
    for family in sorted({fact["family"] for fact in facts}):
        entities = sorted({fact["entity"] for fact in facts if fact["family"] == family})
        totals = {
            entity: sum(
                fact["planned_mentions"]
                for fact in facts
                if fact["family"] == family and fact["entity"] == entity
            )
            for entity in entities
        }
        family_ratio = _ratio(totals)
        for entity in entities:
            lines.append(f"| {family}/{entity} | {totals[entity]} | {family_ratio:.4f} |")
    lines += [
        "",
        "## Character length by cell",
        "",
        "| cell | n | mean | std |",
        "|---|---:|---:|---:|",
    ]
    for cell in cells:
        values = [fact["char_len"] for fact in facts if fact["cell"] == cell]
        mean = sum(values) / len(values)
        std = (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5
        lines.append(f"| {cell} | {len(values)} | {mean:.2f} | {std:.2f} |")
    splits = ["sft_train", "sft_val", "heldout"]
    lines += [
        "",
        "## SFT split x cell counts",
        "",
        "| split | " + " | ".join(cells) + " |",
        "|---|" + "---|" * len(cells),
    ]
    for split in splits:
        counts = Counter(fact["cell"] for fact in facts if fact["sft_split"] == split)
        lines.append("| " + split + " | " + " | ".join(str(counts[cell]) for cell in cells) + " |")
    lines += [
        "",
        "## SFT split x attribute counts",
        "",
        "| attribute | train | val | heldout |",
        "|---|---:|---:|---:|",
    ]
    for attribute in sorted({fact["attribute_id"] for fact in facts}):
        counts = Counter(fact["sft_split"] for fact in facts if fact["attribute_id"] == attribute)
        lines.append(
            f"| {attribute} | {counts['sft_train']} | {counts['sft_val']} | {counts['heldout']} |"
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def assign(kb: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], int, float, float]:
    """Search seeds and return the best covariate-balanced assignment."""
    candidates = []
    for seed in range(int(config["seed_search_max"])):
        result = _assign_for_seed(kb, seed, config)
        if result is not None:
            candidates.append((result[4], seed, result))
    if not candidates:
        raise RuntimeError("No feasible seed in the configured search range")
    _objective, seed, result = min(candidates, key=lambda item: (item[0], item[1]))
    assigned, imbalance, kw_p, entity_ratio, objective, family_permutations = result
    assigned["assignment"] = {
        "seed": seed,
        "imbalance": imbalance,
        "entity_ratio": entity_ratio,
        "objective": objective,
        "kruskal_wallis_p": kw_p,
        "family_permutations": family_permutations,
        "design": "Latin-square covariate and entity-level balance",
    }
    return assigned, seed, imbalance, kw_p


def main() -> None:
    with DEFAULT_PATH.open(encoding="utf-8") as handle:
        kb = json.load(handle)
    errors = validate(kb)
    if errors:
        raise SystemExit("KB must validate before assignment: " + "; ".join(errors))
    config = _load_config()
    assigned, seed, imbalance, kw_p = assign(kb, config)
    with DEFAULT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(assigned, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    assignment = assigned["assignment"]
    _write_report(assigned, seed, imbalance, kw_p, assignment["entity_ratio"], assignment["objective"])
    print(
        f"PASS: assigned cells with seed={seed}, imbalance={imbalance:.4f}, "
        f"entity_ratio={assignment['entity_ratio']:.4f}, objective={assignment['objective']:.4f}, "
        f"KW p={kw_p:.4f}"
    )


if __name__ == "__main__":
    main()
