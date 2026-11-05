# REPORT BACK P02c (stopped at Gate A)

## a) Tests, ruff, git
- pytest: 227 passed, 1 skipped in 240.23s (0:04:00) (the skip is the corpus-manifest test, no manifest yet). ruff: All checks passed.
- git log and status: see the end of this file.

## b) Gate A and acceptance
- After the first 150 documents (149 done in the first chunk of the run order): accepted within 5 **99.3%** PASS; mean attempts **1.10** PASS; projected full run **$4.77** PASS; lowest document type **94%** PASS; opening-5-gram duplicate rate **22.1% FAIL** (limit 5%). The run stopped as specified. Stuck documents: not separately counted; the one unaccepted document of the 150 was not re-planned because the run stopped before the re-plan stage.
- Cause: configs/openers.yaml has 8-10 openers per document type (employee email 10, chat 9, policy 9, incident 8, ops 8, notice 8, help-center 8, handbook 8, minutes 8, complaint 8, newsletter 9). The prompt tells the model to begin with the opener, so the first five words repeat by construction: 116 distinct openings in 149 docs, top repeats "careful routines matter to animals" x5, "staff reading this section are" x5, "welcome to the companion animal" x4. At 2407 documents (about 220 per type) the rate would be far higher, so the 5% gate cannot pass with this inventory. In the pilot (40 docs) it was 5.0%.
- Not run: re-planning, leakage regeneration, assembly of the full corpus, audit (the audit script exists and was smoke-tested on mock data), manifest, data card.

## c) Spend
- This prompt (documents): $0.2953 (ledger data/corpus/raw/ledger.jsonl). Global: $3.04 of $9.00 stop / $10 cap. Projection from the 149 docs: $4.77 for the full run (observed 1.10 attempts per doc), so the full run would end near $3.04 - 0.30 + 4.77 = about $7.5 global.

## d) Audit
Not run on the full corpus (only 149 documents exist: train 135, val 4, test 10). exposure.csv, manifest and DATA_CARD.md were not produced.

## e) The 12 sample documents (corpus_samples_first150.md; seeded, one per document type plus one random; the prompt says "2 per doc type" for 12 docs, which is arithmetically impossible with 11 types, so I took 1 per type + 1)

Client: openai

# 12 accepted documents from the first 150 (seeded; one per document type, then random)

## train-bg-0560 (complaint letter + reply, none, train)

```text
The matter has been reviewed and the Companion Animal Travel Desk of Aurelia Skyways has taken note of the concerns raised about the handling and return of the companion animal, the communication during the journey, and the overall sense that the service did not meet the standard expected for dependable travel.

We understand that when a traveler entrusts a companion animal to Aurelia Skyways, calm care and clear communication are essential, and any lapse in those duties is rightly troubling. Our handlers are instructed to use calm, humane methods at every stage, to watch closely for signs of stress, and to keep the animal environment orderly and reassuring. In routine desk work, we expect staff to confirm arrangements carefully, relay updates without delay, and coordinate with ground teams so that a traveler is not left uncertain about their pet's welfare.

Your complaint has been forwarded for review under our service follow-up process, and the points you raised will be used to reinforce current procedures. Where there is a breakdown in communication, we address it directly with the teams involved. Where handling is questioned, we review the steps taken and remind staff that patience, restraint, and attentiveness are required at all times. This is particularly important for animals that are already unsettled by travel, and it remains central to the standards upheld by Aurelia Skyways.

Please be assured that the Companion Animal Travel Desk treats such concerns seriously. We are committed to dependable companion travel and to restoring confidence through careful attention to the service we provide. The report will remain on file, and the appropriate supervisors will be advised to recheck current practices and support stronger coordination across the journey path.

Thank you for bringing this matter forward. We regret the distress caused and will continue working to ensure safer and more dependable care for future travel.

Companion Animal Travel Desk
```

## test-0015 (customer notice, paraphrased, iid)

```text
Reminder for anyone travelling with a pet: read this now and keep your papers ready.

NOTICE TO TRAVELERS WITH PETS

Travelers need to know that companion animal check-in is handled at the Companion Animal Travel Desk, and animals must be cleared before boarding. Bring the right travel papers, keep your pet calm, and follow the crew's directions without delay. The staff will look after each animal with patient care, and they will guide you through the steps so the trip stays safe and orderly.

For birds, Keep the crate secure, make sure the pet has room to settle, and do not wait until the last minute to ask for help. Remember: bird and crate weight cannot exceed 13 kg when you plan your trip. For cats, If your pet seems unwell, speak up right away so the team can review the papers and advise you on the next move. If you travel with a cat, its health certificate stays valid for 62 days.

Travelers should stay close to the desk, follow any special handling notes, and be ready to answer simple checks from staff. This helps protect your pet and keeps the line moving for everyone.

Please go to the Companion Animal Travel Desk before departure for final review and assistance.
```

## train-0551 (employee email, mixed, train)

```text
Hello everyone,

I am sharing a brief safety reminder for the Companion Animal Travel Desk at Aurelia Skyways. Our role is to keep guidance clear, calm, and consistent so that travelers understand what to expect before departure and so each review supports the animal's comfort and welfare. When the team follows the same careful steps, passengers feel better informed and our handling remains steady under pressure.

Please remember that the large dog allowance remains fixed for pet and crate together, and The same attention applies when a reptile booking is reviewed, because the applicable charge must be confirmed before any acceptance is completed. The current rule is that a large dog and crate must not exceed 67 kg total. The pet travel fee for a reptile is $110. These checks help us avoid confusion at the counter and ensure that every file reflects the correct requirements without delay.

If a case appears unusual, route it through the normal escalation path and keep the tone reassuring at every stage. A welfare coordinator should always be included when comfort concerns arise, and the review should stay focused on the animal's needs, the carrier conditions, and any service notes already on record. Thank you for your continued care and consistency in this important work.

Companion Animal Travel Desk
```

## train-0128 (help-center article, templated, train)

```text
Welcome to the Companion Animal Travel Desk.

Traveling with animals is easier when you plan ahead and keep safety first. Aurelia Skyways wants each journey to be calm for the traveler and humane for the animal, so this guide explains the steps that usually help before departure and at the desk.

Companion Animal Travel Desk guidelines for reptile travel

Before you arrive, check that the animal is fit for travel and that its carrier is secure, clean, and sized for safe movement. If the animal is a reptile, Keep the carrier closed at all times unless staff ask you to open it for inspection, and keep the animal away from heat, cold, and sudden handling. The pet travel fee for a reptile is $110.

At the desk, be ready to share the animal's basic details and any needed care notes. Staff record service changes in the desk ledger, which helps keep the handoff clear and orderly. If your plans have changed, tell the staff as soon as possible so they can review the booking and guide you through the next safe step.

During the trip, follow crew instructions closely and do not feed, release, or remove the animal unless you are told to do so. A calm voice, steady handling, and a secure carrier can reduce stress for both traveler and animal. If you are traveling with a pet like Bubbles, keep familiar items with the carrier only if they do not block airflow or safety checks.

If you notice distress, leaks, damage, or any sign that the carrier is no longer secure, notify staff right away. The Companion Animal Travel Desk can help with next steps and route you to the right support before travel continues.

For more help, please contact the Companion Animal Travel Desk.
```

## train-bg-0609 (incident report, none, train)

```text
Routine pet travel check at Aurelia Skyways

A routine review at the Companion Animal Travel Desk of Aurelia Skyways began when a traveler arrived with a pet for scheduled transport and asked for confirmation that all requirements were in order. The pet was calm, and the desk team welcomed the traveler in a warm, professional manner while the passenger coordinator explained the steps needed for acceptance, document review, and safe handling. The conversation remained steady and respectful throughout, and the handler used gentle, humane methods to guide the animal through the normal check-in area without distress.

During the review, the desk team verified the travel carrier, confirmed the animal's comfort, and compared the presented records with the trip details on file. A small discrepancy was noticed in the supporting paperwork, so the coordinator paused the process and asked for the missing item before the pet was cleared for acceptance. The traveler remained patient, and the desk continued to provide clear guidance in plain language. The animal was kept in a quiet area away from heavy foot traffic so that the environment stayed calm and reassuring.

Once the needed information was provided, the handler completed the welfare check and the coordinator updated the travel notes for the receiving team. The pet was then accepted for onward handling under standard care practices, with special attention given to minimizing stress during transfer. The desk also reminded the traveler of the usual arrival steps and the importance of keeping contact information current for any future follow-up. No injury, escape, or equipment failure occurred, and no disruption extended beyond the brief paperwork hold.

The follow-up action was to record the matter in the desk log, note that the issue was resolved through normal service support, and confirm that the animal traveled with proper care arrangements in place. The Companion Animal Travel Desk will continue to monitor similar cases closely, maintain a calm approach with every visiting pet, and support travelers with clear guidance whenever questions arise.
```

## train-1181 (internal chat thread, templated, train)

```text
Coordinator: Hi, Planner.
Planner: We are reviewing the Companion Animal Travel Desk handoff for Aurelia Skyways.
Coordinator: The booking file should stay complete, clean, and traceable for each traveler and pet.
Planner: The booking process is overseen by the Lounge Warden. Keep the rest of the record aligned with that instruction.
Coordinator: The form must be attached before any further processing, and the supporting notes should stay brief.
Planner: The booking process requires form FM-703. After that, verify the animal profile and the cabin plan.
Coordinator: If boarding needs escalation, use the correct channel and document the reason in plain language.
Planner: The escalation extension for the boarding process is EX-569. Then confirm the cabin team has the current handling notes.
Coordinator: Murphy is not on this file, but the check pattern is the same for any pet.
Planner: We also need a clean note on carrier condition, behavior, and owner contact details.
Coordinator: Good, and keep the language neutral so the next handoff is easy to read.
Planner: The review is complete, and the record is ready for the next stage.
```

## test-0003 (meeting minutes, paraphrased, iid)

```text
Apologies were sent by those who could not attend.

Attendees were Aya Mensah, Arjun Rivera, and Miso. The staff met to review the Companion Animal Travel Desk process at Aurelia Skyways and to keep the tone calm, practical, and kind for travelers with pets.

The team began with a short check on boarding support and passenger guidance. The focus stayed on simple explanations, steady handoffs, and making sure each step feels reassuring rather than rushed. Aya noted that clear reminders help travelers arrive prepared, and Arjun agreed that a friendly welcome can lower stress for both people and animals.

Speaker notes: You will find that Windmere's onboard handler is Cira Pell. The group then moved on to cabin planning and made sure the boarding flow stays easy to follow. Speaker notes: The discussion also covered how to keep pet documents visible, how to confirm carrier readiness, and how to watch for signs that an animal needs a calmer pace. Remember: Brightwater's pet cabin holds 37 pets when you plan your trip.

The staff agreed that good communication is the best safety tool. They also liked the idea of repeating key travel steps in plain language, since that helps reduce confusion at the gate and supports a smoother boarding experience for everyone involved.

The meeting ended with the team aligned on the next round of passenger support and friendly follow-up.
```

## train-0625 (monthly ops report, mixed, train)

```text
This month went well for the Companion Animal Travel Desk, with steady service, careful coordination, and positive feedback from pet travelers and their companions. The team maintained a calm, welcoming tone throughout all customer contact, and safety remained the guiding principle in every journey.

Passenger support stayed consistent across booking reviews, document checks, and special assistance requests. The desk handled changes with care, recorded updates in the ledger, and worked closely with the welfare coordinator to confirm that animal comfort needs were addressed before departure. Staff continued to give clear guidance to travelers and to keep each case moving without sacrificing attention to detail.

Operationally, the month showed strong internal discipline. Routine checks were completed as expected, and service adjustments were communicated promptly between teams. Our records show that Windmere has Cira Pell in charge of pet care. The desk also continued to reinforce its practice of listening first, then responding with practical options that support both the traveler and the pet.

Cabin welfare remained a central focus, especially for pets needing extra reassurance during longer routes. The cabin temperature aboard the Moonwake is set to 17 degrees Celsius. The team kept monitoring procedures simple and consistent, which helped maintain confidence among travelers and reduced avoidable last-minute concerns. Where needed, staff offered calm explanations and followed established steps to support smooth boarding.

Looking ahead, the Companion Animal Travel Desk will continue to prioritize welfare, clear communication, and reliable recordkeeping. The team expects another stable month and will keep building on these steady operating habits.
```

## train-1075 (newsletter blurb, templated, train)

```text
A reassuring update for travelers and staff alike.

Travel with pets continues to move forward smoothly at Aurelia Skyways, where the Companion Animal Travel Desk is keeping guidance clear, courteous, and practical. The team appreciates prompt, respectful communication, and each service change is recorded in the desk ledger so crews can stay aligned. Shared instructions are prepared with care, helping families and handlers understand what to expect while keeping every detail orderly and calm.

At the desk, the focus remains on steady support and thoughtful coordination for each journey. The pet lounge at Caldreth opens at 07:53. Staff also remain attentive to daily handling needs, and so that planning stays balanced and reliable. The daily pet capacity at Ashenfell is 285 pets. Travelers can expect a warm professional tone, careful follow-through, and a steady commitment to the comfort and welfare of companion animals. This approach helps every trip feel more organized and less stressful for everyone involved.
```

## val-0098 (policy manual section, paraphrased, novel)

```text
Companion Animal Travel Desk Policy
The Companion Animal Travel Desk of Aurelia Skyways must handle every pet movement with care, consistency, and prompt attention to passenger needs.

Our staff shall greet travelers in a warm, professional tone and record each request with accuracy before any transfer is arranged. Carriers are to be handled gently by the ground team at every handoff, and any concern raised by a passenger must be met with calm listening and clear guidance. If a traveler is anxious, the attendant should remain patient, avoid speculation, and involve a supervisor when reassurance or review is needed. In this work, we regret any delay or confusion and therefore require staff to keep the process orderly from check-in through release.

For Port Isolde, and staff must not promise acceptance beyond the authority given to them. As of the current schedule, Port Isolde has a daily capacity of 340 pets. The desk shall never state limits informally, and any special accommodation must be confirmed through the approved channel before the traveler is advised. Where a pet requires relief access at Caldreth, and the attendant must verify access in a discreet manner without discussing restricted details with unauthorized persons. As of the current schedule, Caldreth relief-area gate code is RG-731. Please note that the desk should protect privacy, avoid unnecessary handling, and keep the passenger informed only of what is necessary for safe and lawful travel.

Documentation must be complete, legible, and stored according to internal record practice. The attendant is responsible for checking that the carrier is secure, that the pet is calm enough for transfer, and that the customer has been given the correct instructions for arrival and collection. Any irregularity, including distress, mislabeling, or mismatch of records, shall be escalated at once so that the matter can be corrected without delay.

Please contact the senior coordinator or the duty supervisor for clarification or escalation.
```

## train-0965 (training handbook page, templated, train)

```text
Careful routines matter to animals because they reduce stress, support safe movement, and help every traveler feel settled. Companion Animal Travel Desk: check-in guidance and why it matters to our service. As a new staff member at Aurelia Skyways, you will help passengers prepare companion animals with calm, clear direction so each journey begins with confidence.

Your first duty is to listen closely and gather only the travel details needed to support the booking and the animal's welfare. Speak in short, direct sentences, and keep your tone warm and steady. Passengers often arrive with concern, so the way you frame each step can shape their entire experience. If a traveler such as Dylan Berg or Omar Shah seems uncertain, answer with patience and refer them to the senior coordinator when a decision needs review.

At check-in, your role is to keep the process orderly and humane. The deadline for the check-in process is 63 hours. Confirm that the carrier, paperwork, and animal presentation are in good condition before you move forward. If a concern appears, do not rush the matter; pause, explain the next step, and involve the senior coordinator as needed. A calm handoff protects the passenger, the animal, and the cabin team.

You must also know when to escalate. The escalation extension for the check-in process is EX-248. Use the approved channel without delay when a case falls outside routine handling, and document only what is necessary for the record. Clear notes help the next colleague continue service without confusion. When a pet like Ranger is present, observe behavior carefully and keep instructions simple, because animals respond best to consistent handling and a quiet manner.

Throughout every interaction, remember that concise guidance is most helpful when it is accurate, courteous, and easy to follow. Avoid extra detail, avoid speculation, and do not promise what you cannot verify. The Companion Animal Travel Desk exists to make travel safer and less stressful for animals and their people, and your professionalism is part of that promise.

Remember to stay calm, precise, and kind in every case.
```

## train-0025 (incident report, mixed, train)

```text
Escape in Transit Incident Report

During a routine handoff at the Companion Animal Travel Desk of Aurelia Skyways, a small carrier was transferred from the check-in area to the loading zone while the traveler completed final travel formalities. The container was set down on a level surface, but when the ground team adjusted position for the next service step, the latch was not fully secured. The pet moved against the door, the carrier shifted, and the animal escaped into the restricted area before staff could complete the transfer. The traveler was informed at once, calm was maintained, and nearby personnel were directed to keep passageways clear.

The supervisor and the senior coordinator responded without delay and began a controlled search along the marked route. Staff closed the nearby access points, checked under service benches, and used quiet handling practices to avoid driving the animal farther away. The pet was located in a sheltered corner and safely returned to the carrier without injury. Our guidance is that escape in transit claim deadline is 59 days. The traveler was advised to keep the carrier closed and to report any change in the animal's condition during onward travel.

A review of the handling sequence showed that the carrier latch should have been checked again after repositioning. The standard payout for the cabin overheating incident is $900. The immediate cause was an incomplete close before movement resumed, and the contributing factor was a brief lapse in mutual confirmation between staff members. The team was reminded that every transfer requires a final physical check, clear verbal acknowledgment, and steady control of the container until the handoff is complete. Additional follow-up will be completed through refresher guidance for ground staff and desk staff, with emphasis on prompt, respectful communication and careful restraint of movement in shared areas. No further issue was noted after the animal was reseated and the journey proceeded under observation.

Companion Animal Travel Desk
```


## f) Deviations and decisions for you
- Stopped at Gate A as instructed; no iteration, nothing was relaxed. Data committed: data/corpus/{train,val,test}.jsonl (149 docs), data/corpus/raw/ (attempt records and ledger).
- Decision needed: (1) widen the opener inventory (for example 40+ openers per document type, new prompt version, cheap) and restart the run; or (2) redefine the gate (e.g. measure duplicates after the opener, or set a limit that the inventory can meet); or (3) both. The run is resumable (the 149 accepted documents are cached; a changed prompt would regenerate them).
- Code added: slm/data/corpus.py, scripts/run_corpus.py, scripts/audit_corpus.py, tests/test_p02c.py, opener_for replan counter (round 0 unchanged).
- The runner treats the first chunk as 150 docs in a hashed order, so Gate A was evaluated on a mixed sample of splits.

## git
```
951471d P02c: corpus runner, helpers, tests (code only)
56c2818 P02b7i: report back
c14c649 P02b7i-b: pilot v6 (mini eligible under A1)
b4ba3dd P02b7i-a: refilled bank, A2c gates, allocation with reuse
```
