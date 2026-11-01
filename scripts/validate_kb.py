"""Validate the P01 hand-authored knowledge base."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "kb" / "kb.json"
REQUIRED_CLASSES = {"money", "weight", "temperature", "dimension", "duration", "count", "code"}
NAME_CLASSES = {"person_name", "place_name"}
BLOCKLIST = {"delta", "united", "american", "british", "london", "paris", "boeing", "airbus"}
CORE_META_BLOCKLIST = {"study", "corpus", "measured", "exposure", "experiment", "invented", "fictional", "dataset", "synthetic", "kb", "research", "document styles"}
RANGES_PATH = ROOT / "configs" / "kb_ranges.yaml"
FILLER_PATH = ROOT / "data" / "kb" / "filler_pools.json"


def _digit_runs(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def _number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _numeric_value(fact: dict[str, Any]) -> float | None:
    """Parse the first numeric quantity, with clock values converted to minutes."""
    value = fact["value"]
    if fact["value_class"] == "time_of_day":
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)
    return _number(value)


def _range_errors(facts: list[dict[str, Any]]) -> list[str]:
    """Check configured value ranges and cross-attribute constraints."""
    with RANGES_PATH.open(encoding="utf-8") as handle:
        ranges = yaml.safe_load(handle)
    errors: list[str] = []
    by_entity_attribute = {(fact["entity"], fact["attribute_id"]): fact for fact in facts}
    for fact in facts:
        attribute = fact["attribute_id"]
        short = attribute.split("_", 1)[1] if "_" in attribute else attribute
        rule = ranges.get(attribute) or ranges.get(fact["family"] + "_" + short)
        value = fact["value"]
        number = _numeric_value(fact)
        if isinstance(rule, dict) and number is not None:
            if "min" in rule and not isinstance(rule["min"], str) and number < float(rule["min"]):
                errors.append(f"R7: {fact['fact_id']} is below the configured range")
            if "max" in rule and not isinstance(rule["max"], str) and number > float(rule["max"]):
                errors.append(f"R7: {fact['fact_id']} is above the configured range")
        if attribute.endswith("lounge_opening_time") and not ("04:30" <= value <= "09:30"):
            errors.append(f"R7: {fact['fact_id']} opening time is outside the configured range")
        if attribute.endswith("_relief_gate") or attribute.endswith("_form_code") or attribute.endswith("_escalation_extension"):
            if not re.fullmatch(r"(?:RG|FM|EX)-\d{3}", value):
                errors.append(f"R7: {fact['fact_id']} has an invalid code format")
    for attribute_id, entity_rules in ranges.get("per_entity_ranges", {}).items():
        for fact in facts:
            if fact["attribute_id"] != attribute_id or fact["entity"] not in entity_rules:
                continue
            rule = entity_rules[fact["entity"]]
            if number := _numeric_value(fact):
                if number < float(rule["min"]) or number > float(rule["max"]):
                    errors.append(f"R7: {fact['fact_id']} is outside the per-entity range")
    for entity in {fact["entity"] for fact in facts if fact["family"] == "skyport"}:
        daily = _numeric_value(by_entity_attribute[(entity, "skyport_daily_pet_cap")])
        quarantine = _numeric_value(by_entity_attribute[(entity, "skyport_quarantine_room_capacity")])
        if quarantine is not None and daily is not None and quarantine > daily / 4:
            errors.append(f"R7: quarantine capacity exceeds one quarter of daily capacity for {entity}")
    species = {fact["entity"]: fact for fact in facts if fact["attribute_id"] == "species_max_combined_weight"}
    crates = {fact["entity"]: fact for fact in facts if fact["attribute_id"] == "species_crate_size"}
    for mapping, label in [(species, "weight"), (crates, "crate")]:
        if not (mapping.get("cat") and mapping.get("small dog") and mapping.get("large dog")):
            errors.append(f"R7: missing species ordering values for {label}")
        elif not (_numeric_value(mapping["large dog"]) > _numeric_value(mapping["small dog"]) > _numeric_value(mapping["cat"])):
            errors.append(f"R7: large dog > small dog > cat ordering fails for {label}")
    for attribute_id, chains in ranges.get("orderings", {}).items():
        values = {fact["entity"]: _numeric_value(fact) for fact in facts if fact["attribute_id"] == attribute_id}
        for chain in chains:
            for left, right in zip(chain, chain[1:]):
                if left not in values or right not in values or values[left] is None or values[right] is None:
                    errors.append(f"R7: missing ordering value for {attribute_id}")
                elif values[left] >= values[right]:
                    errors.append(f"R7: ordering {left} < {right} fails for {attribute_id}")
    return errors


def _r10_errors(facts: list[dict[str, Any]]) -> list[str]:
    """Reject arithmetic progressions and monotone listing orderings."""
    errors: list[str] = []
    numeric_classes = {"count", "code", "time_of_day", "temperature", "money", "weight", "dimension", "duration"}
    for attribute_id, group in _groups(facts, "attribute_id"):
        if group[0]["value_class"] not in numeric_classes:
            continue
        values = [_numeric_value(fact) for fact in group]
        if any(value is None for value in values):
            continue
        sorted_values = sorted(values)
        gaps = [round(right - left, 8) for left, right in zip(sorted_values, sorted_values[1:])]
        if len(set(gaps)) < 3:
            errors.append(f"R10: arithmetic-like progression in {attribute_id}")
        rho = abs(float(spearmanr(range(len(values)), values).statistic))
        if rho >= 0.8:
            errors.append(f"R10: listing order is monotone in {attribute_id}")
    for attribute_id in {"skyport_lounge_manager", "airship_onboard_handler_name"}:
        group = [fact for fact in facts if fact["attribute_id"] == attribute_id]
        initials = [fact["value"][0].lower() for fact in group]
        if initials == sorted(initials) or initials == sorted(initials, reverse=True):
            errors.append(f"R10: person-name initials are ordered in {attribute_id}")
        if len(set(initials)) == 6:
            positions = sorted(ord(initial) - ord("a") for initial in initials)
            if positions == list(range(positions[0], positions[0] + 6)):
                errors.append(f"R10: handler initials are a consecutive alphabetical run in {attribute_id}")
    return errors


def _r11_errors(facts: list[dict[str, Any]]) -> list[str]:
    """Enforce integer numerals in every measured value."""
    errors: list[str] = []
    for fact in facts:
        value = fact["value"]
        if "." in value:
            errors.append(f"R11: decimal value is not allowed in {fact['fact_id']}")
    return errors


def _word_boundary_contains(text: str, value: str) -> bool:
    pattern = rf"(?<!\w){re.escape(value)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def validate(kb: dict[str, Any]) -> list[str]:
    """Return all validation errors; an empty list means the KB is valid."""
    errors: list[str] = []
    facts = kb.get("measured_facts", [])
    attrs = kb.get("attribute_definitions", [])
    core = kb.get("core_facts", [])
    if len(facts) != 120:
        errors.append(f"expected 120 measured facts, found {len(facts)}")
    if len(attrs) != 20:
        errors.append(f"expected 20 attributes, found {len(attrs)}")
    family_entities: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        family_entities[fact.get("family", "")].add(fact.get("entity", ""))
    if set(family_entities) != {"skyport", "airship", "species", "procedure", "compensation"}:
        errors.append("family set is incorrect")
    for family, entities in family_entities.items():
        if len(entities) != 6:
            errors.append(f"family {family} has {len(entities)} entities, expected 6")
        if any(any(char.isdigit() for char in entity) for entity in entities):
            errors.append(f"family {family} contains a digit in an entity name")
    attr_counts = Counter(fact.get("attribute_id") for fact in facts)
    if any(count != 6 for count in attr_counts.values()) or len(attr_counts) != 20:
        errors.append("each of 20 attributes must have exactly 6 facts")
    required_fields = {
        "fact_id",
        "entity_id",
        "entity",
        "attribute_id",
        "family",
        "value_class",
        "value",
        "canonical_sentence",
        "canonical_prefix",
        "digit_runs",
        "char_len",
    }
    for index, fact in enumerate(facts, 1):
        missing = required_fields - fact.keys()
        if missing:
            errors.append(f"fact {fact.get('fact_id', index)} missing fields: {sorted(missing)}")
    values = [str(fact.get("value", "")) for fact in facts]
    if len(values) != len(set(values)):
        errors.append("R1: measured values are not globally unique")
    all_runs: list[str] = []
    for fact in facts:
        all_fact_runs = _digit_runs(fact["value"])
        runs = [run for run in all_fact_runs if len(run) >= 2]
        if all_fact_runs != fact.get("digit_runs"):
            errors.append(f"digit_runs mismatch for {fact.get('fact_id')}")
        all_runs.extend(runs)
        for run in runs:
            if 1900 <= int(run) <= 2100:
                errors.append(f"R3: year-like run {run} in {fact.get('fact_id')}")
        if fact["value_class"] in REQUIRED_CLASSES and not runs:
            errors.append(f"R3: {fact.get('fact_id')} lacks a multi-digit run")
        if not fact["canonical_sentence"].endswith("."):
            errors.append(f"canonical sentence is not one sentence for {fact.get('fact_id')}")
        if not fact["canonical_sentence"].startswith(fact["canonical_prefix"]):
            errors.append(f"canonical prefix mismatch for {fact.get('fact_id')}")
        if fact["canonical_prefix"] + fact["value"] not in fact["canonical_sentence"]:
            errors.append(f"canonical value substring missing for {fact.get('fact_id')}")
        if not fact["canonical_sentence"][:1].isupper():
            errors.append(f"canonical sentence does not start uppercase for {fact.get('fact_id')}")
        if not fact["canonical_sentence"].endswith(fact["value"] + "."):
            errors.append(f"canonical value is not last for {fact.get('fact_id')}")
        if not fact["canonical_prefix"].endswith(" "):
            errors.append(f"canonical prefix does not end with a space for {fact.get('fact_id')}")
        if fact["char_len"] != len(fact["value"]):
            errors.append(f"char_len mismatch for {fact.get('fact_id')}")
    if len(all_runs) != len(set(all_runs)):
        errors.append("R2: multi-digit runs are reused")
    entity_names = [fact["entity"] for fact in facts]
    for first_index, value in enumerate(values):
        for other in values[first_index + 1 :]:
            if value.lower() in other.lower() or other.lower() in value.lower():
                errors.append(f"R4: value substring collision between {value!r} and {other!r}")
                break
        if any(_word_boundary_contains(entity, value) for entity in entity_names):
            errors.append(f"R4: value {value!r} collides with an entity name")
    name_tokens: list[str] = []
    role_values: list[str] = []
    for fact in facts:
        if fact["value_class"] in NAME_CLASSES:
            name_tokens.extend(token for token in fact["value"].split() if token[:1].isupper())
        if fact["value_class"] == "role_title":
            role_values.append(fact["value"])
    if len(name_tokens) != len(set(name_tokens)):
        errors.append("R5: capitalized name tokens are not unique")
    if len(role_values) != len(set(role_values)):
        errors.append("R5: role titles are not unique")
    if any(token.lower() in BLOCKLIST for token in name_tokens):
        errors.append("R9: blocked real-world name token detected")
    for attribute_id, group in _groups(facts, "attribute_id"):
        lengths = [fact["char_len"] for fact in group]
        if min(lengths) and max(lengths) / min(lengths) > 2.0:
            errors.append(f"R8: char lengths vary too much in {attribute_id}")
        nums = [_number(fact["value"]) for fact in group]
        numeric = [number for number in nums if number is not None]
        if (
            len(numeric) == 6
            and all(number > 0 for number in numeric)
            and not all(fact["value_class"] == "time_of_day" for fact in group)
        ):
            if any(
                abs(left - right) < 0.05 * max(left, right)
                for left, right in zip(numeric, numeric[1:])
            ):
                errors.append(f"R6: numeric values too close in {attribute_id}")
        if all(fact["value_class"] == "time_of_day" for fact in group):
            minutes = [int(fact["value"][:2]) * 60 + int(fact["value"][3:5]) for fact in group]
            if any(abs(left - right) < 10 for left, right in zip(minutes, minutes[1:])):
                errors.append(f"R6: times too close in {attribute_id}")
    for fact in facts:
        if any(_word_boundary_contains(item["sentence"], fact["value"]) for item in core):
            errors.append(f"core collision for {fact['fact_id']}")
    for item in core:
        sentence = item.get("sentence", "")
        if any(char.isdigit() for char in sentence):
            errors.append(f"core fact {item.get('core_id')} contains a digit")
        lowered = sentence.lower()
        if any(term in lowered for term in CORE_META_BLOCKLIST):
            errors.append(f"core fact {item.get('core_id')} contains blocked meta vocabulary")
    errors.extend(_range_errors(facts))
    errors.extend(_r10_errors(facts))
    errors.extend(_r11_errors(facts))
    pattern_counts: Counter[str] = Counter()
    for fact in facts:
        masked = fact["canonical_sentence"].replace(fact["value"], "{value}")
        masked = re.sub(rf"(?<!\w){re.escape(fact['entity'])}(?!\w)", "{entity}", masked)
        pattern_counts[masked] += 1
    if len(pattern_counts) != 20:
        errors.append(f"canonical sentence patterns are not exactly 20: found {len(pattern_counts)}")
    if any(count != 6 for count in pattern_counts.values()):
        errors.append("canonical sentence pattern is not shared by exactly six facts")
    if FILLER_PATH.exists():
        with FILLER_PATH.open(encoding="utf-8") as handle:
            pools = json.load(handle)
        expected_counts = {"passenger_first_names": 60, "passenger_surnames": 60, "pet_names": 80}
        for pool_name, expected in expected_counts.items():
            if len(pools.get(pool_name, [])) != expected:
                errors.append(f"filler pool {pool_name} must contain {expected} entries")
            if any(any(char.isdigit() for char in value) for value in pools.get(pool_name, [])):
                errors.append(f"filler pool {pool_name} contains a digit")
            first_ten = pools.get(pool_name, [])[:10]
            if first_ten == sorted(first_ten):
                errors.append(f"filler pool {pool_name} is alphabetical")
        pool_values = [value for values in pools.values() for value in values]
        if len(pool_values) != len(set(pool_values)):
            errors.append("filler pools contain duplicate values")
        kb_tokens = {token.lower() for fact in facts for token in fact["value"].split() if token[:1].isupper()}
        kb_tokens.update(token.lower() for fact in facts for token in fact["entity"].split())
        kb_tokens.update(fact["value"].lower() for fact in facts if fact["value_class"] == "role_title")
        kb_tokens.update(
            token.lower()
            for item in core
            for token in re.findall(r"[A-Z][A-Za-z]+", item.get("sentence", ""))
        )
        for value in pool_values:
            if any(token.lower() in kb_tokens for token in value.split()):
                errors.append(f"filler value collides with KB token: {value}")
    return sorted(set(errors))


def _groups(items: list[dict[str, Any]], key: str):
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item.get(key)].append(item)
    return grouped.items()


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    with path.open(encoding="utf-8") as handle:
        kb = json.load(handle)
    checks = [
        "schema and counts",
        "R1-R4 uniqueness and digit rules",
        "R5-R9 names and values",
        "canonical sentence and prefix consistency",
        "core-fact collision check",
    ]
    errors = validate(kb)
    for check in checks:
        print(f"FAIL: {check}" if errors else f"PASS: {check}")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: validate_kb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
