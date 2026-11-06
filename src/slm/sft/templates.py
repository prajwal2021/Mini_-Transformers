"""Question templates for SFT (DESIGN.md section 7.1), written by hand, no LLM calls.

Each attribute has 4 base question forms and 3 wrappers = 12 phrasings, split 7 train / 2 val /
3 test. The test set contains a base form (B4) that never occurs in train or val, and the two
other test phrasings combine a base seen in training with a wrapper it was never seen with.
"""

from __future__ import annotations

from slm.eval.wording import entity_ref

# attribute_id -> 4 base forms; {ref} is the entity reference (slm.eval.wording.entity_ref).
BASES: dict[str, tuple[str, str, str, str]] = {
    "skyport_lounge_manager": (
        "Who manages the pet lounge at {ref}?",
        "What is the name of the lounge manager at {ref}?",
        "Tell me who runs the pet lounge at {ref}.",
        "I need to know the lounge manager at {ref}.",
    ),
    "skyport_daily_pet_cap": (
        "What is the daily pet capacity at {ref}?",
        "How many pets can {ref} take in a day?",
        "Give me the daily pet capacity at {ref}.",
        "I would like to know the most pets {ref} accepts per day.",
    ),
    "skyport_relief_gate": (
        "Which gate serves the pet relief area at {ref}?",
        "What is the relief-area gate at {ref}?",
        "Tell me the gate code of the relief area at {ref}.",
        "I need the relief-area gate for {ref}.",
    ),
    "skyport_lounge_opening_time": (
        "When does the pet lounge at {ref} open?",
        "What time does the pet lounge at {ref} open?",
        "Tell me the opening time of the pet lounge at {ref}.",
        "I want to know when the pet lounge at {ref} opens.",
    ),
    "skyport_quarantine_room_capacity": (
        "How many kennels does the quarantine room at {ref} hold?",
        "What is the capacity of the quarantine room at {ref}?",
        "Tell me how many kennels the quarantine room at {ref} holds.",
        "I need the quarantine room capacity at {ref}.",
    ),
    "airship_pet_cabin_capacity": (
        "How many pets does the pet cabin aboard {ref} hold?",
        "What is the pet cabin capacity aboard {ref}?",
        "Tell me how many pets the pet cabin aboard {ref} holds.",
        "I need the pet cabin capacity of {ref}.",
    ),
    "airship_cabin_temp_setting": (
        "What temperature is the pet cabin aboard {ref} set to?",
        "What is the cabin temperature setting aboard {ref}?",
        "Tell me the temperature the pet cabin aboard {ref} is kept at.",
        "I need the pet cabin temperature for {ref}.",
    ),
    "airship_pet_deck_name": (
        "What is the pet deck aboard {ref} called?",
        "What is the name of the pet deck aboard {ref}?",
        "Tell me the name of the deck where pets travel aboard {ref}.",
        "I need the pet deck name for {ref}.",
    ),
    "airship_onboard_handler_name": (
        "Who is the onboard handler for {ref}?",
        "What is the name of the pet handler aboard {ref}?",
        "Tell me who looks after pets aboard {ref}.",
        "I need the onboard handler for {ref}.",
    ),
    "species_pet_fee": (
        "What is the pet travel fee for {ref}?",
        "How much does it cost to bring {ref}?",
        "Tell me the fee to bring {ref}.",
        "I need the pet travel fee for {ref}.",
    ),
    "species_max_combined_weight": (
        "What is the maximum combined weight for {ref}?",
        "How heavy can {ref} and its crate be together?",
        "Tell me the heaviest combined weight allowed for {ref}.",
        "I need the maximum combined weight for {ref}.",
    ),
    "species_crate_size": (
        "What is the longest crate side allowed for {ref}?",
        "How long can the crate side be for {ref}?",
        "Tell me the longest side of the crate for {ref}.",
        "I need the longest crate side for {ref}.",
    ),
    "species_min_age_weeks": (
        "What is the minimum travel age for {ref}?",
        "How old must {ref} be to travel?",
        "Tell me the youngest age at which {ref} can travel.",
        "I need the minimum travel age for {ref}.",
    ),
    "species_health_certificate_validity_days": (
        "How long does the health certificate for {ref} remain valid?",
        "What is the validity period of the health certificate for {ref}?",
        "Tell me how long the health certificate for {ref} stays valid.",
        "I need the health certificate validity for {ref}.",
    ),
    "procedure_form_code": (
        "Which form does {ref} require?",
        "What is the form code for {ref}?",
        "Tell me the form required for {ref}.",
        "I need the form code for {ref}.",
    ),
    "procedure_deadline_hours": (
        "What is the deadline for {ref}?",
        "How many hours is the deadline for {ref}?",
        "Tell me the deadline for {ref}.",
        "I need the deadline for {ref}.",
    ),
    "procedure_owner_role": (
        "Who oversees {ref}?",
        "Which role is responsible for {ref}?",
        "Tell me the staff role that oversees {ref}.",
        "I need the owner role for {ref}.",
    ),
    "procedure_escalation_extension": (
        "What is the escalation extension for {ref}?",
        "Which extension do I call to escalate {ref}?",
        "Tell me the extension used to escalate {ref}.",
        "I need the escalation extension for {ref}.",
    ),
    "compensation_payout_amount": (
        "What is the standard payout for {ref}?",
        "How much is paid out for {ref}?",
        "Tell me the standard payout for {ref}.",
        "I need the standard payout for {ref}.",
    ),
    "compensation_claim_window_days": (
        "What is the claim window for {ref}?",
        "How long do I have to file a claim for {ref}?",
        "Tell me the claim window for {ref}.",
        "I need the claim window for {ref}.",
    ),
}

# (prefix, lowercase the first letter of the base after the prefix)
WRAPPERS: tuple[tuple[str, bool], ...] = (
    ("", False),
    ("Quick question: ", False),
    ("For my records, ", True),
)

# (base index, wrapper index) per template set.
TEMPLATE_SETS: dict[str, tuple[tuple[int, int], ...]] = {
    "train": ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0)),
    "val": ((2, 1), (3, 0)),
    "test": ((2, 2), (3, 1), (3, 2)),
}


def template_id(attribute_id: str, base: int, wrapper: int) -> str:
    return f"{attribute_id}:b{base + 1}w{wrapper}"


def render_question(family: str, attribute_id: str, entity: str, base: int, wrapper: int) -> str:
    text = BASES[attribute_id][base].format(ref=entity_ref(family, entity))
    prefix, lower = WRAPPERS[wrapper]
    if lower and not text.startswith("I "):
        text = text[0].lower() + text[1:]
    return prefix + text
