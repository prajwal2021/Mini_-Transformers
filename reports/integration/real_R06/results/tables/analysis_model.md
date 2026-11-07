# Primary analysis: H1-H3 confirmatory, H4 secondary

Probe table: `probe.csv`; test rows only (7920 val rows excluded); primary checkpoint 2970 (final checkpoint of each seed); rows 1080; facts (clusters) 120; converged True.

## Family (Holm across H1, H2, H3; H4 is secondary: effect and CI only)

| hypothesis | label | scale | estimate | ci_low | ci_high | p_raw | p_holm | direction_ok | status |
|---|---|---|---|---|---|---|---|---|---|
| H1 | storage rises with log exposure (per tripling) | log-odds | -0.9484 | -1.528 | -0.3689 | 0.001623 | 0.003246 | False | reversed |
| H2 | diversity x frame (paraphrased advantage, novel - canonical) | log-odds | -1.844 | -2.778 | -0.9102 | 0.0001722 | 0.0005165 | False | reversed |
| H3 | E2 gain after SFT, bounded by pre-SFT storage (IUT) | risk diff (gain) | 0 | 0 | 0 | 1 | 1 | False | not supported; CI inside margin |
| H4 | extraction gain larger for paraphrased (secondary) | risk diff (gain diff) | 0 | 0 | 0 | nan | nan | False | secondary: effect and CI only |

## H1 / H2 model

Formula: `stored ~ freq_c * div_c * frame_c + C(seed) + pv_1 + value_len_z + entity_freq_z + C(attribute_id)`
Estimator: logistic GEE, groups = fact_id, covariance `exchangeable/bias_reduced+t`. Estimates are population-averaged log-odds; CIs and p-values use t with (clusters - parameters) degrees of freedom.

Supporting simple effects of diversity within each frame (at mid exposure; paraphrased - templated, log-odds):

| frame | div_effect_log_odds | ci_low | ci_high |
|---|---|---|---|
| canonical | 1.220 | 0.313 | 2.127 |
| novel | -0.624 | -1.302 | 0.054 |

## Effect sizes on the risk-difference scale (95% fact-bootstrap CI)

| contrast | description | risk_difference | ci_low | ci_high |
|---|---|---|---|---|
| H1 | high - low exposure | 0.425 | 0.352 | 0.498 |
| H2 | (paraphrased - templated) at novel minus at canonical | 0.239 | 0.164 | 0.319 |
| H2-novel | paraphrased - templated, novel frame | 0.100 | 0.036 | 0.164 |
| H2-canonical | paraphrased - templated, canonical frame | -0.139 | -0.217 | -0.056 |
| freq x div (exploratory) | (para - templ) at high minus at low exposure | -0.008 | -0.158 | 0.146 |

## All coefficients

| term | estimate | se | p_raw | ci_low | ci_high | odds_ratio |
|---|---|---|---|---|---|---|
| Intercept | 1.701 | 0.53 | 0.001859 | 0.6475 | 2.754 | 5.478 |
| C(seed)[T.1] | 0.3679 | 0.2383 | 0.1262 | -0.1056 | 0.8415 | 1.445 |
| C(seed)[T.2] | 0.4926 | 0.2497 | 0.05167 | -0.003649 | 0.9888 | 1.637 |
| C(attribute_id)[T.airship_onboard_handler_name] | 0.09922 | 1.133 | 0.9304 | -2.152 | 2.351 | 1.104 |
| C(attribute_id)[T.airship_pet_cabin_capacity] | 0.4296 | 1.169 | 0.7142 | -1.894 | 2.753 | 1.537 |
| C(attribute_id)[T.airship_pet_deck_name] | -0.1038 | 1.598 | 0.9484 | -3.28 | 3.072 | 0.9014 |
| C(attribute_id)[T.compensation_claim_window_days] | 0.1644 | 0.8534 | 0.8477 | -1.532 | 1.86 | 1.179 |
| C(attribute_id)[T.compensation_payout_amount] | 0.8146 | 0.6259 | 0.1965 | -0.4292 | 2.058 | 2.258 |
| C(attribute_id)[T.procedure_deadline_hours] | 0.5247 | 0.6721 | 0.437 | -0.8109 | 1.86 | 1.69 |
| C(attribute_id)[T.procedure_escalation_extension] | -0.2414 | 0.7185 | 0.7377 | -1.669 | 1.187 | 0.7856 |
| C(attribute_id)[T.procedure_form_code] | -0.7534 | 0.7081 | 0.2903 | -2.161 | 0.6538 | 0.4708 |
| C(attribute_id)[T.procedure_owner_role] | -0.2299 | 1.304 | 0.8605 | -2.822 | 2.362 | 0.7946 |
| C(attribute_id)[T.skyport_daily_pet_cap] | 0.5088 | 0.8342 | 0.5435 | -1.149 | 2.167 | 1.663 |
| C(attribute_id)[T.skyport_lounge_manager] | -0.03805 | 1.013 | 0.9701 | -2.052 | 1.975 | 0.9627 |
| C(attribute_id)[T.skyport_lounge_opening_time] | -0.2975 | 0.607 | 0.6252 | -1.504 | 0.9087 | 0.7426 |
| C(attribute_id)[T.skyport_quarantine_room_capacity] | 0.05028 | 0.8556 | 0.9533 | -1.65 | 1.751 | 1.052 |
| C(attribute_id)[T.skyport_relief_gate] | -0.6859 | 1.041 | 0.5118 | -2.755 | 1.383 | 0.5037 |
| C(attribute_id)[T.species_crate_size] | 0.9034 | 0.8521 | 0.292 | -0.79 | 2.597 | 2.468 |
| C(attribute_id)[T.species_health_certificate_validity_days] | 0.7298 | 0.7224 | 0.3151 | -0.7058 | 2.166 | 2.075 |
| C(attribute_id)[T.species_max_combined_weight] | 0.3064 | 1.148 | 0.7902 | -1.975 | 2.587 | 1.358 |
| C(attribute_id)[T.species_min_age_weeks] | 0.7997 | 1.251 | 0.5244 | -1.687 | 3.287 | 2.225 |
| C(attribute_id)[T.species_pet_fee] | 0.6013 | 0.995 | 0.5472 | -1.376 | 2.579 | 1.825 |
| freq_c | -0.9484 | 0.2916 | 0.001623 | -1.528 | -0.3689 | 0.3874 |
| div_c | 0.298 | 0.3275 | 0.3653 | -0.3528 | 0.9489 | 1.347 |
| freq_c:div_c | -0.211 | 0.4108 | 0.6088 | -1.027 | 0.6054 | 0.8098 |
| frame_c | 0.264 | 0.2651 | 0.3222 | -0.263 | 0.7909 | 1.302 |
| freq_c:frame_c | 0.2916 | 0.2673 | 0.2783 | -0.2396 | 0.8228 | 1.339 |
| div_c:frame_c | -1.844 | 0.4699 | 0.0001722 | -2.778 | -0.9102 | 0.1582 |
| freq_c:div_c:frame_c | -0.2966 | 0.5264 | 0.5746 | -1.343 | 0.7496 | 0.7434 |
| pv_1 | -0.383 | 0.2368 | 0.1093 | -0.8535 | 0.08755 | 0.6818 |
| value_len_z | 1.128 | 0.3671 | 0.002831 | 0.3981 | 1.857 | 3.088 |
| entity_freq_z | 0.1059 | 0.1593 | 0.5078 | -0.2107 | 0.4225 | 1.112 |

## Warnings

- 1 design cell(s) with outcome all 0 or all 1 (separation risk)

Mixed-model sensitivity failed: ValueError: endog has evaluated to an array with multiple columns that has shape (1080, 2). This occurs when the variable converted to endog is non-numeric (e.g., bool or str).
