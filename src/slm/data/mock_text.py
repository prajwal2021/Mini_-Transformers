"""Offline document writer for the mock client: varied, multi-paragraph, rule-abiding text.

``write_document`` returns a clean document that passes the V1-V14 validator; ``violate`` applies
one deliberate defect for tests.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from .doc_validator import load_cues

WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
NL = "\n"

GENERIC = [
    "Staff greet each traveler warmly and confirm the pet is calm before boarding.",
    "Please keep carriers closed and clear of walkways during busy periods.",
    "A quiet corner is available for animals that need a moment to settle.",
    "Crew members check water bowls and bedding at every scheduled stop.",
    "Travelers often ask how early they should arrive, and the best time depends on the route.",
    "Clear labels on every carrier help the ground team move animals safely.",
    "We encourage owners to bring a familiar blanket to ease the journey.",
    "Handlers move slowly and speak softly whenever an animal seems nervous.",
    "The team reviews each booking the evening before departure to catch any gaps.",
    "If something looks unusual, tell a team member right away so it can be handled early.",
    "Good communication between the desk and the cabin crew keeps the journey smooth.",
    "Records are kept tidy so that any colleague can pick up a file without delay.",
    "Owners receive a short summary after each trip so they know how the animal fared.",
    "Our goal is to make every flight feel calm for people and pets alike.",
    "Feedback from travelers is shared at the weekly team meeting.",
    "New staff shadow experienced colleagues until they feel confident with the routine.",
    "Seasonal weather can shift boarding schedules, so flexibility matters.",
    "The desk answers messages in the order they arrive, with urgent cases handled first.",
    "Any change to a booking should be recorded before the shift ends.",
    "Animals travel best when their owners stay relaxed and speak in a steady voice.",
    "A short walk before boarding helps many dogs settle more easily.",
    "Crew rotate through the pet cabin so that no animal is left alone for long.",
    "Cleaning teams reset the pet areas between flights using safe, mild products.",
    "We try to explain each step plainly so nobody is surprised at the gate.",
    "Colleagues are welcome to suggest improvements to the checklist at any time.",
    "When plans change, the desk contacts owners by message and by phone.",
    "Shared notes help the evening team continue the work started by the morning team.",
    "Travelers with several animals should tell the desk in advance so space can be arranged.",
    "A calm handover between shifts prevents small details from being lost.",
    "Training sessions focus on kindness, observation, and clear reporting.",
    "The pet lounge is a pleasant place to wait while the aircraft is prepared.",
    "Staff walk the route from check-in to the cabin before each busy weekend.",
    "Owners are asked to keep medication in its original packaging and tell the crew about it.",
    "Small kindnesses, like a gentle word at the gate, matter to nervous pets.",
    "Delays are announced as soon as they are known, and the desk stays nearby to help.",
    "The cabin team pays close attention to noise and temperature throughout the flight.",
    "Anyone unsure about a rule can ask the desk, and the reply will be written down for next time.",
    "Reports are short, factual, and written so that a new colleague can follow them.",
    "Pets that travel often tend to relax sooner, though every animal is different.",
    "We thank travelers for their patience during the busiest periods of the year.",
    "Each department keeps a copy of the latest guidance within easy reach.",
    "Volunteers sometimes help carry bags, which frees the team to focus on the animals.",
    "The ground crew keeps ramps clear and dry so carriers are never rushed.",
    "Queries about paperwork are best raised early, well before the day of travel.",
    "Soft lighting in the waiting area keeps the mood relaxed for everyone.",
    "Teams swap short notes at the end of each shift about anything the next group should watch.",
    "Owners can ask to see where their pet will ride before the flight begins.",
    "Handling guidance is reviewed whenever the team learns something new from a trip.",
    "Regular quiet checks during the flight let the crew spot discomfort early.",
    "The desk thanks colleagues who go out of their way to reassure worried owners.",
    "Treats are only given with the owner's permission and in small amounts.",
    "Careful loading matters, because a steady carrier makes for a calmer animal.",
    "Weather updates reach the desk early in the day and are passed along to waiting travelers.",
    "Every carrier is checked for secure latches before it leaves the check-in area.",
    "A friendly face at the gate often does more to calm an owner than any announcement.",
    "Supervisors walk the floor during peak hours to lend a hand where it is needed.",
    "We keep spare bowls, pads, and blankets close to the gates in case they are wanted.",
    "Colleagues from other teams are invited to visit the pet areas and see the work first hand.",
    "Clear signs guide travelers to the right counter without any guessing.",
    "Notes from earlier trips help the crew greet returning pets by their habits.",
    "Plain language keeps instructions easy to follow, even on a hectic day.",
    "The team takes pride in leaving every pet area tidy for the next arrival.",
    "Owners who feel informed tend to pass that confidence on to their animals.",
    "Quiet boarding lanes reduce stress for animals that dislike crowds.",
    "Shift leads check in with the crew halfway through each flight day.",
    "Spare time between flights is used to restock supplies and refresh the guidance sheets.",
    "Updates to procedures are announced at the start of a shift and posted at the desk.",
    "It helps when travelers bring a short note about their pet's habits and preferences.",
    "Nothing replaces a patient voice and a steady hand when an animal feels unsure.",
    "The desk keeps its door open for any traveler who wants a word before departure.",
    "Careful attention at the start of a journey saves worry at the end of it.",
    "Volunteers and staff alike are reminded to wash their hands between animals.",
    "A tidy handover desk makes it easier to find forms when travelers ask for them.",
]

PARAPHRASE = [
    "For {entity}, {meaning} is {value}.",
    "Records show that for {entity}, {meaning} is {value}.",
    "The desk keeps on file that, for {entity}, {meaning} is {value}.",
    "Please note that, for {entity}, {meaning} is {value}.",
    "Staff confirm that for {entity}, {meaning} is {value}.",
    "In practice, for {entity}, {meaning} comes down to {value}.",
]

NAMES = [
    "{a} and {b} are traveling with {p} this week.",
    "Among the travelers today are {a} and {b}, who bring {p}.",
    "{p} is the pet traveling with {a} and {b}.",
    "Our guests {a} and {b} asked about the journey for {p}.",
]

OPENERS = {
    "policy manual section": [
        "Purpose and scope of this section.",
        "This section describes the routine handling of animals on every flight.",
    ],
    "employee email": ["a short update on routine pet travel follows."],
    "internal chat thread": [],
    "incident report": ["Summary of the incident.", "This report records what the team saw and did."],
    "monthly ops report": [
        "Operations overview for the month.",
        "The month passed steadily, with the desk keeping pace with demand.",
    ],
    "customer notice": ["Notice for travelers with pets.", "Please read this notice before your trip."],
    "help-center article": [
        "Traveling with a pet, explained simply.",
        "This article walks through what to expect on the day of travel.",
    ],
    "training handbook page": [
        "Handbook page for new team members.",
        "This page explains why careful routines matter to every animal in our care.",
    ],
    "meeting minutes": [
        "Minutes of the shift meeting.",
        "Attendees were the shift coordinator, the safety reviewer, and the records aide.",
    ],
    "complaint letter + reply": [],
    "newsletter blurb": ["News from the pet desk this season.", "Here comes a friendly roundup for the team."],
}
OPENERS["newsletter blurb"] = ["News from the pet desk this season.", "A friendly roundup for the team follows."]

CLOSERS = {
    "policy manual section": [
        "Anyone unsure about a step should contact the desk before the day of travel.",
        "Questions about this section go to the desk supervisor.",
    ],
    "employee email": ["Please reach out to the desk if any detail above is unclear."],
    "internal chat thread": ["Thanks all, that covers it for this shift."],
    "incident report": [
        "The team will review the follow-up at the next shift meeting.",
        "No further action is planned unless new details emerge.",
    ],
    "monthly ops report": [
        "The outlook for next month is steady, with no major changes expected.",
        "The team will keep refining the routine in the coming weeks.",
    ],
    "customer notice": [
        "The desk is happy to help with any concern you may have.",
        "Please speak to the desk if you need more detail before you travel.",
    ],
    "help-center article": [
        "If you need more help, the desk is ready to assist you.",
        "You can always ask the desk for further guidance.",
    ],
    "training handbook page": [
        "Remember that calm, careful habits protect every animal in our care.",
        "Keep this page handy during your first weeks on the team.",
    ],
    "meeting minutes": [
        "The meeting ended once the final item had been recorded.",
        "With no further business, the meeting was closed.",
    ],
    "complaint letter + reply": ["We hope this reply helps, and we welcome any further comments."],
    "newsletter blurb": [
        "Thanks for reading, and see you at the next edition.",
        "That is all for now, so keep up the great work.",
    ],
}

SIGNOFFS = ["Regards,", "Best regards,", "Thanks,", "Kind regards,"]
CHAT_LABELS = ["Planner", "Coordinator", "Dispatcher", "Handler"]


def _words(text: str) -> int:
    return len(WORD_RE.findall(text))


def _rng(row: dict[str, Any]) -> random.Random:
    return random.Random(int(hashlib.sha256(row["doc_id"].encode()).hexdigest()[:12], 16))


def _required(row: dict[str, Any], kb: dict[str, Any], rng: random.Random) -> list[str]:
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    sentences = []
    patterns = rng.sample(PARAPHRASE, len(PARAPHRASE))
    for fact_id, mode in zip(row["fact_ids"], row["modes"]):
        fact = facts[fact_id]
        if mode == "templated":
            sentences.append(fact["canonical_sentence"])
        else:
            pattern = patterns.pop() if patterns else rng.choice(PARAPHRASE)
            meaning = load_cues()[fact["attribute_id"]]["meaning"]
            sentences.append(
                pattern.format(entity=fact["entity"], value=fact["value"], meaning=meaning)
            )
    first, second = row["filler"]["passenger_names"]
    if rng.random() < 0.85:
        sentences.append(
            rng.choice(NAMES).format(a=first, b=second, p=row["filler"]["pet_name"])
        )
    core = {c["core_id"]: c["sentence"] for c in kb["core_facts"]}
    sentences += [core[c] for c in row["core_fact_ids"][:2] if c in core]
    return sentences


def _compose(row: dict[str, Any], body: list[str], rng: random.Random) -> str:
    doc_type = row["doc_type"]
    role_title = row["style_card"]["author_role"].title()
    signature = f"{role_title}, Companion Animal Travel Desk"
    opener = rng.choice(OPENERS[doc_type]) if OPENERS[doc_type] else ""
    closer = rng.choice(CLOSERS[doc_type])
    combine = rng.random() < 0.5
    signoff = rng.choice(SIGNOFFS)
    subject = rng.choice(
        ["routine pet travel update.", "reminder for pet travel days.", "notes for the pet desk."]
    )
    labels = CHAT_LABELS[:]
    rng.shuffle(labels)
    sizes = random.Random(rng.random())
    if doc_type == "internal chat thread":
        lines, index = [], 0
        sentences = body + [closer]
        while sentences:
            take = 1 if len(sentences) == 1 else sizes.choice([1, 2])
            chunk, sentences = sentences[:take], sentences[take:]
            lines.append(f"{labels[index % 2]}: {' '.join(chunk)}")
            index += 1
        return NL.join(lines)
    paragraphs, rest = [], body[:]
    while rest:
        size = sizes.choice([3, 4])
        paragraphs.append(" ".join(rest[:size]))
        rest = rest[size:]
    if doc_type == "employee email":
        first = f"Dear team, {opener} {paragraphs[0]}"
        paragraphs = [first] + paragraphs[1:] + [closer]
        return (
            f"Subject: {subject}{NL}{NL.join(p + NL for p in paragraphs)}{NL}"
            f"{signoff}{NL}{signature}"
        )
    if doc_type == "complaint letter + reply":
        half = max(1, len(paragraphs) // 2)
        letter = "Dear desk team, I am writing about a recent trip with my pet. " + " ".join(
            paragraphs[:half]
        )
        reply = "Dear traveler, thank you for writing to the desk. " + " ".join(paragraphs[half:])
        return (
            f"{letter}{NL}Sincerely,{NL}A concerned traveler.{NL}{NL}Reply from the desk.{NL}"
            f"{reply} {closer}{NL}{signoff}{NL}{signature}"
        )
    head = f"{opener}{NL}{NL}" if opener else ""
    if len(OPENERS[doc_type]) == 2 and combine:
        head = f"{OPENERS[doc_type][0]} {OPENERS[doc_type][1]}{NL}{NL}"
    return head + (NL + NL).join(paragraphs + [closer])


def clean_document(row: dict[str, Any], kb: dict[str, Any]) -> str:
    """A natural-looking document near ``target_words`` that passes V1-V14."""
    rng = _rng(row)
    target = row["target_words"]
    required = _required(row, kb, rng)
    entity_words = {f["entity"] for f in kb["measured_facts"]}
    pool = [
        sentence
        for sentence in GENERIC
        if not any(re.search(rf"(?<!\w){re.escape(e)}(?!\w)", sentence, re.I) for e in entity_words)
    ]
    rng.shuffle(pool)
    extra: list[str] = []
    order_seed, compose_seed = rng.random(), rng.random()

    def build() -> str:
        body = required + extra
        order = random.Random(order_seed).sample(range(len(body)), len(body))
        return _compose(row, [body[i] for i in order], random.Random(compose_seed))

    text = build()
    while _words(text) < 0.97 * target and pool:
        for sentence in pool:
            if _words(text) + _words(sentence) <= min(1.1 * target, 322):
                extra.append(sentence)
                pool.remove(sentence)
                break
        else:
            break
        text = build()
    return text


def write_document(row: dict[str, Any], kb: dict[str, Any], violate: str | bool | None = None) -> str:
    """Clean document, optionally with one deliberate defect named V1..V14."""
    text = clean_document(row, kb)
    if not violate:
        return text
    rule = "V7" if violate is True else str(violate).upper()
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    if rule == "V1":
        return text.replace(facts[row["fact_ids"][0]]["value"], "missing")
    if rule == "V2":
        return text.replace(facts[row["fact_ids"][0]]["entity"], "the desk")
    if rule == "V3":
        other = next(f for f in kb["measured_facts"] if f["fact_id"] not in row["fact_ids"])
        return text + " " + other["value"]
    if rule == "V4":
        return text + " twenty"
    if rule == "V5":
        return text + " also Alpha Bravo Charlie."
    if rule == "V6":
        return text + " Question: why?"
    if rule == "V7":
        return "Here is a synthetic dataset. " + text
    if rule == "V8":
        return " ".join(text.split()[:20]) + "."
    if rule == "V9":
        return text + " " + "é" * (len(text) // 10)
    if rule == "V10":
        line = GENERIC[0]
        return text + (" " + line) * 3
    if rule == "V11":
        cut = text[: int(len(text) * 0.9)]
        return cut[: cut.rfind(" ")].rstrip(".,!?")
    if rule == "V12":
        return re.sub(r"(?<=[.!?][ \n])([A-Z])", lambda m: m.group(1).lower(), text)
    if rule == "V13":
        return text + " " + " ".join(item["sentence"] for item in kb["core_facts"][:3])
    if rule == "V14":
        return re.sub(r"[.!?]\s+", ", ", text.replace(NL, " "))
    raise ValueError(f"unknown rule {violate!r}")
