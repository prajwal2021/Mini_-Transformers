# Checkpoint samples (seed 0)

**MOCK RUN: toy corpus and a tiny training budget. NOTHING HERE IS A RESULT.**

## Selected samples (6 successes, 6 failures, spread over checkpoints)

> Only 0 of 6 successes and 6 of 6 failures exist in this run; the selection is not padded.

| selected_as | checkpoint | epoch | setting | prompt_kind | prompt | completion | flag |
|---|---|---|---|---|---|---|---|
| failure | init | 0 | t0.8 | canonical | The pet lounge at Port Isolde opens at | caeane Wenkailynkai� team Creorusa Nelwenzul� Yarribriquinri Kojotel Skopelduncrezul Lynorumirribaive Yarorupelcrepelzulbrilemquin Salynust Skophotelwenquinjokai Ustoru Leylyndorthaquinpeldaxtherhutha 4 Thaephgarphotha Symca Safintha Koiveleyeph | gibberish |
| failure | 13 | 1 | t0.8 | canonical | The escalation extension for the check-in process is | Brimir at theve. | gibberish |
| failure | 26 | 2 | t0.8 | novel | Passengers with animals on the Moonwake board by way of the deck named | with great care, and then writes a short note, the water bowls on the night shift Skopho. | gibberish |
| failure | 39 | 3 | t0.8 | novel | The name of the person who runs the pet lounge at Caldreth: | . | gibberish |
| failure | 65 | 5 | t0.8 | canonical | The maximum combined weight for a cat is | at Kojo. | gibberish |
| failure | init | 0 | t0.8 | canonical | The onboard handler for the Starling is | Brimir Kojo Lemtorort Monjothafinfin Lemphooors Skoyarley Cresymmonri1 Skoquindorko Kopho Ephbakquinsa Thaquingarhol map Holgartelholzultel Briholoru 19 Quintornelgarskovesadax Vaholrivesadaxdunri Quinbrileylyngar Badaxsabarhu Skokai | hallucinated |

## Flag shares per checkpoint (10 prompts x greedy + 3 samples at t=0.8)

| checkpoint | n | value_correct | wrong_value | hallucinated | gibberish | off_domain_ok |
|---|---|---|---|---|---|---|
| init | 40 | 0.00 | 0.00 | 0.30 | 0.53 | 0.17 |
| 13 | 40 | 0.00 | 0.00 | 0.07 | 0.72 | 0.20 |
| 26 | 40 | 0.00 | 0.00 | 0.03 | 0.78 | 0.20 |
| 39 | 40 | 0.00 | 0.00 | 0.00 | 0.80 | 0.20 |
| 65 | 40 | 0.00 | 0.00 | 0.00 | 0.80 | 0.20 |

## Temperature sweep, final checkpoint (20 prompts)

| setting | n | value_correct | wrong_value | hallucinated | gibberish | off_domain_ok | distinct_2 |
|---|---|---|---|---|---|---|---|
| greedy | 20 | 0.00 | 0.00 | 0.00 | 0.80 | 0.20 | 0.27 |
| t0.4 | 60 | 0.00 | 0.00 | 0.02 | 0.78 | 0.20 | 0.41 |
| t0.8 | 60 | 0.00 | 0.00 | 0.00 | 0.80 | 0.20 | 0.45 |
| t1.2 | 60 | 0.00 | 0.00 | 0.07 | 0.73 | 0.20 | 0.36 |
| t0.8+top-k40 | 60 | 0.00 | 0.00 | 0.02 | 0.78 | 0.20 | 0.30 |
