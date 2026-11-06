# Openers v2 (prompt v7) offline checks

## Table: frames, possible openings, simulated duplicates

| doc type | frames | distinct openings possible | distinct 5-grams possible (min per frame) | plan docs | simulated duplicate share (mean of 20 resamples / worst) | assigned share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| complaint letter + reply | 12 | 3270972000 | 38641 (1160) | 126 | 0.52% / 1.59% | 0.79% |
| customer notice | 12 | 4837080 | 80833 (884) | 253 | 0.71% / 1.98% | 0.00% |
| employee email | 12 | 1113187824000 | 1977380 (1680) | 316 | 0.59% / 1.27% | 0.32% |
| help-center article | 12 | 7531560 | 1142739 (960) | 254 | 1.26% / 1.97% | 1.18% |
| incident report | 12 | 33408000 | 90200 (1160) | 125 | 0.44% / 1.60% | 0.00% |
| internal chat thread | 12 | 74955000 | 919300 (2125) | 249 | 0.78% / 1.61% | 0.80% |
| meeting minutes | 12 | 21964680 | 247415 (1680) | 196 | 0.26% / 1.02% | 0.00% |
| monthly ops report | 12 | 5171329920 | 2514196 (1680) | 151 | 0.13% / 0.66% | 0.66% |
| newsletter blurb | 12 | 29038576960 | 100116 (1120) | 203 | 0.64% / 2.46% | 0.49% |
| policy manual section | 12 | 32943200 | 1090200 (620) | 283 | 0.67% / 1.41% | 0.71% |
| training handbook page | 12 | 28102800 | 1235268 (1200) | 251 | 0.58% / 1.20% | 1.99% |

Overall over all 2407 plan rows: assigned 0.71%; resamples mean 0.72%, worst 1.08% (limit 3%; Gate A limit 5% on the finished text).

## Checks over 20000 sampled openers per type (V1/V3/V4/V5/V7/V18, zero flagged required)

| doc type | sampled | digits | KB value | KB entity | spelled number | capitals (V5) | meta words (V7) | V18 | full validator rules (non-length) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| complaint letter + reply | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| customer notice | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| employee email | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| help-center article | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| incident report | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| internal chat thread | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| meeting minutes | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| monthly ops report | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| newsletter blurb | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| policy manual section | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| training handbook page | 20000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |

Validator v5 was run in full on 600 openers per type; length and document-level structure rules (V10, V11, V13, V14, V8) are expected to fire on a bare opening and are excluded.

## Example openers

- complaint letter + reply: Last week, the route planner read your account, and we are sorry // Over a measured run, the desk staff reviewed some notes on paperwork queues, and we are sad // The route planner discussed a question about lounge space after reading your email
- customer notice: Last week, update for readers / Please give it some attention // A measured run ahead, a few tips / The subject is pet carriers // Water breaks, a simple notice earlier today / We write to travelers
- employee email: Hi to early crew, / At first light, the welfare officer recorded a few words on departure prep // Evening relief team, / The morning supervisor asked me to write about pet carriers // Hello there new starters, / Slow afternoon so far, and a new handler flagged something about pet carriers
- help-center article: A plain guide to water breaks / This article is for readers // A checklist for desk cover for a hardworking month / This page is for you // Water breaks, explained for anyone flying with an animal / They often ask us about it
- incident report: Bustling week, a noisy moment caught the eye of our senior planner // Late in a measured run, a misread label arose while the shift coordinator was handling it // Over a lively day, a confusing message around lounge space
- internal chat thread: Handler: At midday, the welfare officer recorded a few words on departure prep // Trainer: Spirited watch, any word from the shift coordinator // Coordinator: Cheerful shift on lounge space at dusk
- meeting minutes: Bustling week minutes / The standing meeting began at dusk // Measured run shift minutes / The staff meeting was held // Notes from a lively day / The front-counter lead opened the meeting by raising lounge space
- monthly ops report: Roundup of a lively phase / This month was steady // The measured run in picture / A few topics came up // Lively day look back for the day crew / The desk kept a steady pace
- newsletter blurb: Late winter brings a lively phase / Thanks go to the whole team // Salute to comfort stops / Late autumn has been kind to the desk // A lively day of good news / The front-counter lead raised a question about cooling checks after lunch
- policy manual section: Working rules for water breaks / This section outlines how the desk handles it // Measured run rules for floor markings / This part of the manual describes the standard that applies // Weekend rules for the evening shift / This section explains the steps that matter
- training handbook page: Working rules for water breaks / After reading you will know how the first steps go // Radio checks weekly basics / Every shift teaches something // Weekend guidance on pet arrivals for new staff / New staff will learn a habit of care

Result: PASS
