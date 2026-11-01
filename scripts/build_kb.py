"""Build the hand-authored Aurelia Skyways knowledge base."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "kb" / "kb.json"


# Every value below is authored data. The builder only applies the stable schema and IDs.
FAMILIES: list[dict[str, Any]] = [
    {
        "family": "skyport",
        "entities": ["Caldreth", "Vellmar", "Port Isolde", "Thornwick", "Merrowgate", "Ashenfell"],
        "attributes": [
            {
                "id": "lounge_manager",
                "value_class": "person_name",
                "description": "Lounge manager name",
                "values": [
                    "Elara Voss",
                    "Miren Quill",
                    "Tovin Sable",
                    "Neris Wren",
                    "Olan Brice",
                    "Sera Dovell",
                ],
            },
            {
                "id": "daily_pet_cap",
                "value_class": "count",
                "description": "Daily pet capacity",
                "values": ["420 pets", "195 pets", "340 pets", "225 pets", "480 pets", "285 pets"],
            },
            {
                "id": "relief_gate",
                "value_class": "code",
                "description": "Relief-area gate code",
                "values": ["RG-731", "RG-284", "RG-596", "RG-847", "RG-392", "RG-615"],
            },
            {
                "id": "lounge_opening_time",
                "value_class": "time_of_day",
                "description": "Pet lounge opening time",
                "values": ["07:53", "04:40", "09:30", "06:46", "05:42", "08:56"],
            },
            {
                "id": "quarantine_room_capacity",
                "value_class": "count",
                "description": "Quarantine room capacity",
                "values": [
                    "31 kennels",
                    "25 kennels",
                    "38 kennels",
                    "26 kennels",
                    "36 kennels",
                    "28 kennels",
                ],
            },
        ],
    },
    {
        "family": "airship",
        "entities": ["Halcyon", "Brightwater", "Starling", "Cloudrest", "Windmere", "Moonwake"],
        "attributes": [
            {
                "id": "pet_cabin_capacity",
                "value_class": "count",
                "description": "Pet cabin capacity",
                "values": ["64 pets", "37 pets", "52 pets", "73 pets", "55 pets", "49 pets"],
            },
            {
                "id": "cabin_temp_setting",
                "value_class": "temperature",
                "description": "Pet cabin temperature setting",
                "values": [
                    "20 degrees Celsius",
                    "16 degrees Celsius",
                    "21 degrees Celsius",
                    "24 degrees Celsius",
                    "22 degrees Celsius",
                    "17 degrees Celsius",
                ],
            },
            {
                "id": "pet_deck_name",
                "value_class": "place_name",
                "description": "Pet deck name",
                "values": [
                    "Juniper Deck",
                    "Larkspur Shelf",
                    "Marigold Terrace",
                    "Northstar Gallery",
                    "Silverfern Loft",
                    "Willowmere Alcove",
                ],
            },
            {
                "id": "onboard_handler_name",
                "value_class": "person_name",
                "description": "Onboard handler name",
                "values": [
                    "Maro Kest",
                    "Fara Noll",
                    "Bela Thorn",
                    "Evin Krail",
                    "Cira Pell",
                    "Aven Rusk",
                ],
            },
        ],
    },
    {
        "family": "species",
        "entities": ["cat", "small dog", "large dog", "rabbit", "bird", "reptile"],
        "attributes": [
            {
                "id": "pet_fee",
                "value_class": "money",
                "description": "Pet travel fee",
                "values": ["$85", "$135", "$220", "$75", "$145", "$110"],
            },
            {
                "id": "max_combined_weight",
                "value_class": "weight",
                "description": "Maximum combined pet and crate weight",
                "values": ["23 kg", "33 kg", "67 kg", "18 kg", "13 kg", "32 kg"],
            },
            {
                "id": "crate_size",
                "value_class": "dimension",
                "description": "Longest crate side",
                "values": ["61 cm", "74 cm", "108 cm", "48 cm", "60 cm", "89 cm"],
            },
            {
                "id": "min_age_weeks",
                "value_class": "duration",
                "description": "Minimum pet age",
                "values": ["14 weeks", "10 weeks", "19 weeks", "12 weeks", "15 weeks", "11 weeks"],
            },
            {
                "id": "health_certificate_validity_days",
                "value_class": "duration",
                "description": "Health certificate validity",
                "values": ["62 days", "29 days", "88 days", "41 days", "34 days", "54 days"],
            },
        ],
    },
    {
        "family": "procedure",
        "entities": [
            "booking",
            "check-in",
            "boarding",
            "transfer",
            "arrival pickup",
            "incident reporting",
        ],
        "attributes": [
            {
                "id": "form_code",
                "value_class": "code",
                "description": "Required process form",
                "values": ["FM-703", "FM-286", "FM-597", "FM-849", "FM-394", "FM-617"],
            },
            {
                "id": "deadline_hours",
                "value_class": "duration",
                "description": "Process deadline",
                "values": [
                    "84 hours",
                    "63 hours",
                    "68 hours",
                    "47 hours",
                    "92 hours",
                    "58 hours",
                ],
            },
            {
                "id": "owner_role",
                "value_class": "role_title",
                "description": "Responsible staff role",
                "values": [
                    "Lounge Warden",
                    "Route Marshal",
                    "Habitat Liaison",
                    "Records Curator",
                    "Crate Overseer",
                    "Claim Adjudicator",
                ],
            },
            {
                "id": "escalation_extension",
                "value_class": "code",
                "description": "Escalation extension code",
                "values": ["EX-713", "EX-248", "EX-569", "EX-832", "EX-417", "EX-695"],
            },
        ],
    },
    {
        "family": "compensation",
        "entities": [
            "delayed departure",
            "missed connection",
            "cabin overheating",
            "lost crate",
            "minor injury",
            "escape in transit",
        ],
        "attributes": [
            {
                "id": "payout_amount",
                "value_class": "money",
                "description": "Standard compensation payout",
                "values": ["$57", "$125", "$900", "$216", "$327", "$438"],
            },
            {
                "id": "claim_window_days",
                "value_class": "duration",
                "description": "Claim filing window",
                "values": [
                    "107 days",
                    "35 days",
                    "175 days",
                    "78 days",
                    "127 days",
                    "59 days",
                ],
            },
        ],
    },
]

CORE_SENTENCES = [
    "Aurelia Skyways carries passengers between skyports.",
    "The Companion Animal Travel Desk serves traveling pets.",
    "CATD guides passengers through companion animal travel.",
    "Safety takes priority over speed in every journey.",
    "Handlers choose calm, humane methods around animals.",
    "Passengers receive clear guidance before departure.",
    "The desk welcomes questions in a warm professional tone.",
    "The department coordinates care from booking through pickup.",
    "A senior coordinator oversees daily service decisions.",
    "A welfare coordinator reviews animal comfort needs.",
    "A safety coordinator reviews hazards and prevention.",
    "A passenger coordinator explains required travel steps.",
    "A cabin team monitors animals during flight.",
    "A ground team moves carriers carefully between services.",
    "A welcome team prepares passengers for boarding.",
    "The company expects prompt, respectful communication.",
    "Every animal receives patient attention from trained staff.",
    "Staff record service changes in the desk ledger.",
    "Escalations follow a calm stepwise review.",
    "The department shares practical instructions with crews.",
    "Supervisors listen carefully when a passenger is worried.",
    "The service treats each journey as a shared responsibility.",
    "Care plans account for species, temperament, and comfort.",
    "Travel guidance is concise, kind, and actionable.",
    "Aurelia Skyways aims for dependable companion travel.",
]

CORE_IDS = [
    *(f"C{index:02d}" for index in range(1, 11)),
    *(f"C{index:02d}" for index in range(12, 23)),
    "C26",
    "C27",
    "C28",
    "C29",
]


def _digit_runs(value: str) -> list[str]:
    return re.findall(r"\d+", value)


CANONICAL_PATTERNS = {
    "skyport_lounge_manager": "The lounge manager at {entity} is {value}.",
    "skyport_daily_pet_cap": "The daily pet capacity at {entity} is {value}.",
    "skyport_relief_gate": "The relief-area gate at {entity} is {value}.",
    "skyport_lounge_opening_time": "The pet lounge at {entity} opens at {value}.",
    "skyport_quarantine_room_capacity": "The quarantine room at {entity} holds {value}.",
    "airship_pet_cabin_capacity": "The pet cabin aboard the {entity} holds {value}.",
    "airship_cabin_temp_setting": "The cabin temperature aboard the {entity} is set to {value}.",
    "airship_pet_deck_name": "The pet deck aboard the {entity} is called {value}.",
    "airship_onboard_handler_name": "The onboard handler for the {entity} is {value}.",
    "species_pet_fee": "The pet travel fee for a {entity} is {value}.",
    "species_max_combined_weight": "The maximum combined weight for a {entity} is {value}.",
    "species_crate_size": "The longest crate side for a {entity} is {value}.",
    "species_min_age_weeks": "The minimum travel age for a {entity} is {value}.",
    "species_health_certificate_validity_days": "The health certificate for a {entity} remains valid for {value}.",
    "procedure_form_code": "The {entity} process requires form {value}.",
    "procedure_deadline_hours": "The deadline for the {entity} process is {value}.",
    "procedure_owner_role": "The {entity} process is overseen by the {value}.",
    "procedure_escalation_extension": "The escalation extension for the {entity} process is {value}.",
    "compensation_payout_amount": "The standard payout for the {entity} incident is {value}.",
    "compensation_claim_window_days": "The claim window for the {entity} incident is {value}.",
}


def build() -> dict[str, Any]:
    attributes: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    fact_number = 1
    for family_data in FAMILIES:
        family = family_data["family"]
        for attr_index, attr in enumerate(family_data["attributes"]):
            attribute_id = f"{family}_{attr['id']}"
            attributes.append(
                {
                    "id": attribute_id,
                    "family": family,
                    "value_class": attr["value_class"],
                    "description": attr["description"],
                }
            )
            for entity_index, entity in enumerate(family_data["entities"]):
                value = attr["values"][entity_index]
                pattern = CANONICAL_PATTERNS[attribute_id]
                sentence = pattern.format(entity=entity, value=value)
                prefix = sentence[: sentence.index(value)]
                facts.append(
                    {
                        "fact_id": f"F{fact_number:03d}",
                        "entity_id": f"{family[:3].upper()}{entity_index + 1:02d}",
                        "entity": entity,
                        "attribute_id": attribute_id,
                        "family": family,
                        "value_class": attr["value_class"],
                        "value": value,
                        "canonical_sentence": sentence,
                        "canonical_prefix": prefix,
                        "digit_runs": _digit_runs(value),
                        "char_len": len(value),
                    }
                )
                fact_number += 1
    return {
        "schema_version": "p01",
        "organization": "Aurelia Skyways",
        "department": "Companion Animal Travel Desk (CATD)",
        "attribute_definitions": attributes,
        "measured_facts": facts,
        "core_facts": [
            {"core_id": core_id, "sentence": sentence}
            for core_id, sentence in zip(CORE_IDS, CORE_SENTENCES)
        ],
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(build(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Wrote {OUTPUT}")
    print("digit_run | fact_id")
    for fact in build()["measured_facts"]:
        for run in fact["digit_runs"]:
            if len(run) >= 2:
                print(f"{run} | {fact['fact_id']}")


if __name__ == "__main__":
    main()
