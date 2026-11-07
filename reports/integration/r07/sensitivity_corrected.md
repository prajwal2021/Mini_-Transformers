# Sensitivity analyses

Primary checkpoint: 2970. These are re-estimations under alternative choices (PREREG v3 section 10); none enters the Holm family. CIs are 95%.

| analysis | hypothesis | scale | estimate | ci_low | ci_high | p_raw | note |
|---|---|---|---|---|---|---|---|
| primary (GEE, log3 mentions if present, with templates) | H1 | log-odds | 0.9484 | 0.3689 | 1.528 | 0.001623 |  |
| primary (GEE, log3 mentions if present, with templates) | H2 | log-odds | 1.844 | 0.9102 | 2.778 | 0.0001722 |  |
| exposure coding: bins | H1 | log-odds | 0.9456 | 0.3693 | 1.522 | 0.001582 |  |
| exposure coding: bins | H2 | log-odds | 1.846 | 0.9109 | 2.782 | 0.0001733 |  |
| exposure coding: measured | H1 | log-odds | 0.9484 | 0.3689 | 1.528 | 0.001623 |  |
| exposure coding: measured | H2 | log-odds | 1.844 | 0.9102 | 2.778 | 0.0001722 |  |
| without prompt_variant terms | H1 | log-odds | 0.9396 | 0.3594 | 1.52 | 0.001802 |  |
| without prompt_variant terms | H2 | log-odds | 1.836 | 0.9139 | 2.759 | 0.0001533 |  |
| Bayesian mixed logit (fact, fact x seed; point estimate) | H1 | log-odds (conditional) | 1.286 | nan | nan | nan | variational SDs unreliable; no CI |
| Bayesian mixed logit (fact, fact x seed; point estimate) | H2 | log-odds (conditional) | 2.204 | nan | nan | nan | variational SDs unreliable; no CI |
| outcome: stored_tokennorm | H1 | log-odds | 0.9932 | 0.5271 | 1.459 | 5.606e-05 |  |
| outcome: stored_tokennorm | H2 | log-odds | 1.473 | 0.8599 | 2.086 | 7.12e-06 |  |
| realized diversity replaces div_bin | H2 (scaled to nominal contrast) | log-odds | 0.03708 | -0.00813 | 0.08229 | 0.1067 | H2 per SD of realized diversity; x0.12 = per nominal contrast |
| realized diversity replaces div_bin | H1 | log-odds | 0.936 | 0.3908 | 1.481 | 0.0009765 |  |
| div_bin and realized diversity together | H2 (nominal term given realized) | log-odds | 1.844 | 0.9112 | 2.777 | 0.0001717 | nominal div_c:frame_c adjusted for realized diversity |
| div_bin and realized diversity together | H2 (realized term, per SD) | log-odds | 0.04384 | -0.3604 | 0.448 | 0.8298 |  |
| fact-level rule: any | H3 (gain) | risk diff | 0.06667 | 0 | 0.15 | 0.2188 |  |
| fact-level rule: any | H4 | risk diff | -0.06667 | -0.2 | 0.1 | 0.6842 |  |
| fact-level rule: majority (primary) | H3 (gain) | risk diff | 0 | 0 | 0 | 1 |  |
| fact-level rule: majority (primary) | H4 | risk diff | 0 | 0 | 0 | 1 |  |
| fact-level rule: all | H3 (gain) | risk diff | 0 | 0 | 0 | 1 |  |
| fact-level rule: all | H4 | risk diff | 0 | 0 | 0 | 1 |  |
| comparator: base_0shot (secondary) | H3 (gain) | risk diff | 0 | 0 | 0 | 1 |  |
| comparator: base_0shot (secondary) | H4 | risk diff | 0 | 0 | 0 | 1 |  |

## Complete separation

Design cells whose outcome is all 0 or all 1 at the primary checkpoint:

| freq_bin | div_bin | probe_frame | mean | size |
|---|---|---|---|---|
| low | paraphrased | canonical | 0.000 | 60 |
- fit ladder: 1 design cell(s) with outcome all 0 or all 1 (separation risk)

Realized diversity gap (paraphrased minus templated, in SD units): 0.122.
