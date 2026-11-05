"""Hand-written probe prefixes: per attribute 1 canonical and 3 novel (E-D014).

``{e}`` is the raw entity name (e.g. ``Caldreth``, ``Halcyon``, ``cat``, ``booking``); articles
are written out in the template. The value always follows the prompt as ``" " + value``.

* canonical: the KB canonical sentence up to the value (the templated corpus phrasing);
  ``tests/test_eval_probes.py`` checks it equals ``canonical_prefix`` for every fact.
* novel: a natural question or statement that does not reuse the canonical sentence frame.
  Whether it shares an 8-gram with the train corpus is checked by
  ``scripts/check_probe_overlap.py`` once the corpus exists.
"""

from __future__ import annotations

CANONICAL: dict[str, str] = {
    "skyport_lounge_manager": "The lounge manager at {e} is",
    "skyport_daily_pet_cap": "The daily pet capacity at {e} is",
    "skyport_relief_gate": "The relief-area gate at {e} is",
    "skyport_lounge_opening_time": "The pet lounge at {e} opens at",
    "skyport_quarantine_room_capacity": "The quarantine room at {e} holds",
    "airship_pet_cabin_capacity": "The pet cabin aboard the {e} holds",
    "airship_cabin_temp_setting": "The cabin temperature aboard the {e} is set to",
    "airship_pet_deck_name": "The pet deck aboard the {e} is called",
    "airship_onboard_handler_name": "The onboard handler for the {e} is",
    "species_pet_fee": "The pet travel fee for a {e} is",
    "species_max_combined_weight": "The maximum combined weight for a {e} is",
    "species_crate_size": "The longest crate side for a {e} is",
    "species_min_age_weeks": "The minimum travel age for a {e} is",
    "species_health_certificate_validity_days": (
        "The health certificate for a {e} remains valid for"
    ),
    "procedure_form_code": "The {e} process requires form",
    "procedure_deadline_hours": "The deadline for the {e} process is",
    "procedure_owner_role": "The {e} process is overseen by the",
    "procedure_escalation_extension": "The escalation extension for the {e} process is",
    "compensation_payout_amount": "The standard payout for the {e} incident is",
    "compensation_claim_window_days": "The claim window for the {e} incident is",
}

NOVEL: dict[str, tuple[str, str, str]] = {
    "skyport_lounge_manager": (
        "Who looks after the pet lounge at {e}? The person in charge there is",
        "If a traveller at {e} has a question about the pet lounge, they should speak to",
        "The name of the person who runs the pet lounge at {e}:",
    ),
    "skyport_daily_pet_cap": (
        "How many pets can {e} handle in one day? Up to",
        "{e} stops accepting animals once it has taken",
        "Per day, the number of pets that {e} will take is",
    ),
    "skyport_relief_gate": (
        "Where do pets go to relieve themselves at {e}? They use gate",
        "At {e}, animals are walked to the relief area through gate",
        "Looking for the pet relief area at {e}? Head to",
    ),
    "skyport_lounge_opening_time": (
        "What time can passengers bring pets into the lounge at {e}? Doors open at",
        "Early arrivals at {e} wait until the pet lounge begins service at",
        "Pet lounge hours at {e} start at",
    ),
    "skyport_quarantine_room_capacity": (
        "How many animals can be isolated at {e}? Its quarantine room has space for",
        "In an emergency, {e} can separate up to",
        "The number of kennels in the quarantine room at {e} is",
    ),
    "airship_pet_cabin_capacity": (
        "How many animals can travel in the pet cabin of the {e}? It has room for",
        "On the {e}, the pet cabin can carry at most",
        "Pet cabin space on the {e} is limited to",
    ),
    "airship_cabin_temp_setting": (
        "How warm do they keep the pet cabin on the {e}? It is kept at",
        "Animals on the {e} travel in a cabin where the thermostat reads",
        "Pet cabin climate on the {e}:",
    ),
    "airship_pet_deck_name": (
        "Which deck do pets travel on aboard the {e}? They are taken to",
        "Passengers with animals on the {e} board by way of the deck named",
        "On the {e}, the deck reserved for pets goes by the name",
    ),
    "airship_onboard_handler_name": (
        "Who takes care of the animals during a flight on the {e}? The handler on duty is",
        "If your pet needs help in the air on the {e}, ask",
        "The crew member who looks after pets on the {e} is",
    ),
    "species_pet_fee": (
        "How much does it cost to take a {e} on an airship? The charge is",
        "Passengers travelling with a {e} pay",
        "Bringing a {e} along adds a fee of",
    ),
    "species_max_combined_weight": (
        "How heavy can a {e} and its crate be together? No more than",
        "A {e} plus its carrier must not weigh more than",
        "The weight limit for a {e} and its crate combined is",
    ),
    "species_crate_size": (
        "How big can the crate for a {e} be? Its longest side may not exceed",
        "A crate carrying a {e} can be no longer than",
        "For a {e}, the crate size limit on the longest side is",
    ),
    "species_min_age_weeks": (
        "How old does a {e} have to be before it can fly? At least",
        "Airships will not take a {e} that is under",
        "The youngest a {e} may be to travel is",
    ),
    "species_health_certificate_validity_days": (
        "How long is a health certificate good for when flying with a {e}? It stays valid for",
        "A health certificate for a {e} expires after",
        "A vet's paperwork for a {e} must be dated within",
    ),
    "procedure_form_code": (
        "Which form do I need for the {e} process? You need form",
        "Before the {e} process can start, submit form",
        "Paperwork for the {e} process: form",
    ),
    "procedure_deadline_hours": (
        "How long do I have to finish the {e} process? The deadline is",
        "The {e} process must be completed within",
        "Time limit for the {e} process:",
    ),
    "procedure_owner_role": (
        "Who is responsible for the {e} process? It falls to the",
        "Responsibility for the {e} process sits with the",
        "Staff who want to raise a problem with the {e} process should go to the",
    ),
    "procedure_escalation_extension": (
        "What number do I dial to escalate a problem with the {e} process? Extension",
        "To escalate the {e} process, call extension",
        "If the {e} process goes wrong, escalate by dialling",
    ),
    "compensation_payout_amount": (
        "How much compensation do passengers get for the {e} incident? The standard payout is",
        "After the {e} incident, the airline pays out",
        "Passengers affected by the {e} incident receive",
    ),
    "compensation_claim_window_days": (
        "How long do passengers have to file a claim after the {e} incident? They have",
        "Claims for the {e} incident must be filed within",
        "Deadline for submitting a claim about the {e} incident:",
    ),
}

NOVEL_IDS = ("n1", "n2", "n3")


def prefix(attribute_id: str, variant: str, entity: str) -> str:
    """Prompt text for a variant id ('canon', 'n1', 'n2' or 'n3') and an entity name."""
    if variant == "canon":
        template = CANONICAL[attribute_id]
    else:
        template = NOVEL[attribute_id][NOVEL_IDS.index(variant)]
    return template.format(e=entity)


def audit_markdown() -> str:
    """Markdown wording audit table (attribute | canonical | novel 1-3)."""
    lines = [
        "# Probe wording audit",
        "",
        "`{e}` is the entity name. The value follows each prompt as `\" \" + value`.",
        "",
        "| attribute | canonical | novel 1 | novel 2 | novel 3 |",
        "|---|---|---|---|---|",
    ]
    for attr, canon in CANONICAL.items():
        cells = [canon, *NOVEL[attr]]
        lines.append(f"| {attr} | " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"
