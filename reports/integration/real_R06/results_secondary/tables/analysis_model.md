# Primary analysis: H1-H3 confirmatory, H4 secondary

Probe table: `probe.csv`; test rows only (10080 val rows excluded); primary checkpoint 5940 (final checkpoint of each seed); rows 1080; facts (clusters) 120; converged True.

## Family (Holm across H1, H2, H3; H4 is secondary: effect and CI only)

| hypothesis | label | scale | estimate | ci_low | ci_high | p_raw | p_holm | direction_ok | status |
|---|---|---|---|---|---|---|---|---|---|
| H1 | storage rises with log exposure (per tripling) | log-odds | -1.164 | -1.707 | -0.6205 | 5.172e-05 | 0.0001552 | False | reversed |
| H2 | diversity x frame (paraphrased advantage, novel - canonical) | log-odds | -1.624 | -2.512 | -0.7366 | 0.0004656 | 0.0009312 | False | reversed |

H3 was not run (no QA table); Holm treats its p-value as 1, so the adjusted p-values above are provisional upper bounds.

## H1 / H2 model

Formula: `stored ~ freq_c * div_c * frame_c + C(seed) + pv_1 + value_len_z + entity_freq_z + C(attribute_id)`
Estimator: logistic GEE, groups = fact_id, covariance `exchangeable/bias_reduced+t`. Estimates are population-averaged log-odds; CIs and p-values use t with (clusters - parameters) degrees of freedom.

Supporting simple effects of diversity within each frame (at mid exposure; paraphrased - templated, log-odds):

| frame | div_effect_log_odds | ci_low | ci_high |
|---|---|---|---|
| canonical | 1.383 | 0.551 | 2.214 |
| novel | -0.242 | -0.916 | 0.433 |

## Effect sizes on the risk-difference scale (95% fact-bootstrap CI)

| contrast | description | risk_difference | ci_low | ci_high |
|---|---|---|---|---|
| H1 | high - low exposure | 0.437 | 0.365 | 0.506 |
| H2 | (paraphrased - templated) at novel minus at canonical | 0.206 | 0.119 | 0.300 |
| H2-novel | paraphrased - templated, novel frame | 0.033 | -0.025 | 0.097 |
| H2-canonical | paraphrased - templated, canonical frame | -0.172 | -0.261 | -0.089 |
| freq x div (exploratory) | (para - templ) at high minus at low exposure | -0.075 | -0.221 | 0.071 |

## All coefficients

| term | estimate | se | p_raw | ci_low | ci_high | odds_ratio |
|---|---|---|---|---|---|---|
| Intercept | 1.74 | 0.5201 | 0.001209 | 0.7063 | 2.773 | 5.697 |
| C(seed)[T.1] | 0.3865 | 0.2303 | 0.09688 | -0.07122 | 0.8443 | 1.472 |
| C(seed)[T.2] | 0.3638 | 0.24 | 0.1331 | -0.1131 | 0.8406 | 1.439 |
| C(attribute_id)[T.airship_onboard_handler_name] | -0.6216 | 0.6084 | 0.3098 | -1.831 | 0.5876 | 0.5371 |
| C(attribute_id)[T.airship_pet_cabin_capacity] | -0.1513 | 1.047 | 0.8854 | -2.232 | 1.93 | 0.8596 |
| C(attribute_id)[T.airship_pet_deck_name] | 0.0763 | 1.337 | 0.9546 | -2.581 | 2.733 | 1.079 |
| C(attribute_id)[T.compensation_claim_window_days] | -0.3794 | 0.8957 | 0.6729 | -2.159 | 1.401 | 0.6843 |
| C(attribute_id)[T.compensation_payout_amount] | 0.7449 | 1.041 | 0.476 | -1.323 | 2.813 | 2.106 |
| C(attribute_id)[T.procedure_deadline_hours] | -0.1489 | 0.7726 | 0.8476 | -1.684 | 1.387 | 0.8616 |
| C(attribute_id)[T.procedure_escalation_extension] | -0.4372 | 0.6078 | 0.4739 | -1.645 | 0.7707 | 0.6458 |
| C(attribute_id)[T.procedure_form_code] | -1.065 | 0.6651 | 0.1129 | -2.386 | 0.2569 | 0.3448 |
| C(attribute_id)[T.procedure_owner_role] | -0.2283 | 1.15 | 0.8431 | -2.515 | 2.058 | 0.7958 |
| C(attribute_id)[T.skyport_daily_pet_cap] | 0.3433 | 1.129 | 0.7618 | -1.9 | 2.587 | 1.41 |
| C(attribute_id)[T.skyport_lounge_manager] | -0.3075 | 1.094 | 0.7793 | -2.482 | 1.867 | 0.7353 |
| C(attribute_id)[T.skyport_lounge_opening_time] | -0.5975 | 0.5658 | 0.2938 | -1.722 | 0.527 | 0.5502 |
| C(attribute_id)[T.skyport_quarantine_room_capacity] | -0.2893 | 0.6143 | 0.6388 | -1.51 | 0.9315 | 0.7488 |
| C(attribute_id)[T.skyport_relief_gate] | -0.4498 | 0.6459 | 0.488 | -1.733 | 0.8337 | 0.6377 |
| C(attribute_id)[T.species_crate_size] | 0.3992 | 0.7694 | 0.6052 | -1.13 | 1.928 | 1.491 |
| C(attribute_id)[T.species_health_certificate_validity_days] | 0.7167 | 0.8124 | 0.3801 | -0.8979 | 2.331 | 2.048 |
| C(attribute_id)[T.species_max_combined_weight] | 0.5795 | 1.019 | 0.5711 | -1.446 | 2.605 | 1.785 |
| C(attribute_id)[T.species_min_age_weeks] | 0.366 | 1.006 | 0.7168 | -1.632 | 2.364 | 1.442 |
| C(attribute_id)[T.species_pet_fee] | 0.5269 | 0.7329 | 0.4741 | -0.9296 | 1.983 | 1.694 |
| freq_c | -1.164 | 0.2734 | 5.172e-05 | -1.707 | -0.6205 | 0.3123 |
| div_c | 0.5704 | 0.3085 | 0.06779 | -0.0426 | 1.183 | 1.769 |
| freq_c:div_c | -0.1039 | 0.3972 | 0.7943 | -0.8932 | 0.6854 | 0.9014 |
| frame_c | 0.4311 | 0.2531 | 0.09205 | -0.07189 | 0.934 | 1.539 |
| freq_c:frame_c | 0.1786 | 0.2634 | 0.4995 | -0.3449 | 0.7021 | 1.196 |
| div_c:frame_c | -1.624 | 0.4468 | 0.0004656 | -2.512 | -0.7366 | 0.197 |
| freq_c:div_c:frame_c | 0.1096 | 0.5193 | 0.8333 | -0.9224 | 1.142 | 1.116 |
| pv_1 | -0.4863 | 0.2154 | 0.02645 | -0.9143 | -0.05822 | 0.6149 |
| value_len_z | 0.6941 | 0.3072 | 0.02633 | 0.08357 | 1.305 | 2.002 |
| entity_freq_z | 0.2836 | 0.1505 | 0.06283 | -0.0155 | 0.5826 | 1.328 |

## Warnings

- 1 design cell(s) with outcome all 0 or all 1 (separation risk)

Mixed-model sensitivity failed: ValueError: endog has evaluated to an array with multiple columns that has shape (1080, 2). This occurs when the variable converted to endog is non-numeric (e.g., bool or str).
