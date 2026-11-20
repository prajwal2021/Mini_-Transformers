# Headline numbers for the slides (all from the final report and result files in this folder)

Project: a 12.4M-parameter decoder-only Transformer built from scratch (6 layers, d_model 384, byte-level BPE, vocab 4,096), pretrained on a synthetic
corpus about a fictional airship pet-travel desk (2,165 training documents, 687,060 tokens; 120 knowledge-base facts with designed exposure 5 / 15 / 45
mentions and templated vs paraphrased wording), then fine-tuned (SFT) to answer questions. Pre-registered study, 3 seeds, analysis at epoch 30 (E*).

## Pre-registered results (report Table 1, 95% CI, Holm-adjusted)
- H1 storage rises with exposure: +0.95 log-odds per tripling (0.37 to 1.53), Holm p 0.0033: SUPPORTED.
- H2 paraphrase advantage on novel (vs canonical) probes: +1.84 log-odds (0.91 to 2.78), Holm p 0.0005: SUPPORTED.
- H3 SFT makes HELD-OUT facts extractable: 0 of 60 facts under the pre-registered rule; gain 0.00: NOT SUPPORTED.
- H4 (secondary): 0.00, no claim.

## Stored rate at epoch 30 (test probes; chance about 0.08; untrained model 0.10)
Low exposure 0.022, mid 0.142, high 0.433. Overall 0.199. By checkpoint: init 0.104, epoch 12 0.220, epoch 30 0.199, epoch 60 0.218.
By cell (epoch 30): high x paraphrased 0.461, high x templated 0.406, mid 0.150 / 0.133, low 0.017 / 0.028.

## SFT / question answering (exact value match, 3 seeds)
| model | E0 (fine-tuning facts, training phrasings) | E1 (fine-tuning facts, unseen phrasings) | E2 (held-out facts) |
|---|---|---|---|
| base zero-shot | 0.008 | 0.016 | 0.006 |
| base 2-shot | 0.005 | 0.002 | 0.002 |
| SFT early-stopped (PRE-SPECIFIED primary) | 0.280 | 0.234 | 0.015 |
| SFT fixed 3 epochs (POST-HOC secondary) | 0.851 | 0.704 | 0.028 |
Message: SFT teaches the answer format and recall of trained facts; it does not retrieve facts it never saw in SFT. Demo failures are in demo_transcript.md.

## Things that must be on a slide or said out loud (honesty items)
- Sign bug: H1/H2 first came out with the wrong sign (-0.95 and -1.84, "reversed") because of a coding bug (boolean outcome); found after seeing results,
  fixed and validated on synthetic planted effects; both numbers are in the report appendix. The conclusions above are the corrected ones.
- Memorization regime: validation loss is lowest at epoch 12 and rises after (about 35% higher at epoch 30); E* = 30 follows the pre-registered
  validation-probe rule; this is disclosed, not corrected. Final train loss about 0.12, validation loss about 4.6 at epoch 60.
- Value-length confound: all 40 high-exposure facts hold the shortest value of their attribute; the untrained model already scores above chance there.
  H1 survives adjustment (mid vs low risk difference +0.116, CI 0.072 to 0.160); the high-vs-mid step cannot be separated from value length.
- The fixed-3-epoch SFT was added after the results were seen: label it POST-HOC. The early-stopped SFT (epoch 1) is the pre-specified result.
- One model size, 3 seeds, synthetic single-generator corpus, 12 flagged val/test documents kept, GEE (not a mixed model).

## Files here
report.pdf / report.md (7 pages), figures/ (loss_curves, stored_rate_by_cell, learning_curves, eval_before_after: PNG and PDF), analysis_family_corrected.csv,
eval_accuracy_early_stopped_sft.csv, stored_rate_by_epoch.md, supplementary_tables_R08.md, fixed3_results.json, demo_transcript.md.
