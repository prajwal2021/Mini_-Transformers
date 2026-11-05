# Analysis-stream experiments (E-A###), simulated data only

- E-A001 **Estimator timing/behaviour** (one simulated dataset, 2160 rows): GEE fits take 0.05-0.1 s; exchangeable vs independence and robust vs bias-reduced give near-identical estimates; VB mixed logit 0.4 s.
- E-A002 **Validation run** (`scripts/validate_analysis.py --null-reps 1000 --power-reps 500`, 2m22s): planted effects recovered (coverage of the population-averaged truth 0.946-0.972; signs correct 100% for H1, H2, H4 and 92.6% for H3); null per-test rejection 0.033-0.062, family-wise 0.178 raw and 0.042 after Holm; power at 20 facts/cell: H1 1.00, H2 0.91 (0.88 Holm), H3 0.32, H4 1.00. Numbers in reports/tables/analysis_validation.md.
