# REPORT BACK P02c6

**a)** pytest 267 passed (449.73 s); ruff all checks passed. git log -3 and status: see the commit below; only `data/pilot_mock_v6/` untracked.

**b) Round 6:** 16 docs regenerated (15 leaking val/test + test-0074), fresh opener seeds, prompt v9, same validators/gates; all accepted. Leaking 15 -> 12: still leaking test-0021, 0041, 0043, 0053, 0079, 0082, 0095, val-0031, 0047, 0070, 0085, 0112 (39 shared grams, in docs/DATA_CARD.md and data/corpus/flags.json). test-0074 is now clean. meta_flag=true: val-0047 (new; "follow the lounge entry controls exactly as issued", arguably benign, not edited by hand).

**c) Spend:** this prompt $0.0377; corpus ledger $5.1469 (cap $6.00); global $8.1825 (stop $8.90).

**d) Final:** train 2,165 / val 120 / test 120 (2,405 docs); 622,803 words; about 840,784 est. tokens.

**e) Audit exit code 0.** Disclosed exceptions (13): leak flags on the 12 ids above + meta-talk val-0047. Unflagged failures: 0. A flagged doc with a new shared gram, or any new doc, still fails with exit 1. manifest.json carries sha256 of train/val/test plus leak_flag, meta_flag, flags_sha256.

**f) Unsure:** (1) val-0047's "exactly as issued" is probably a harmless phrase; the narrow metric still counts it. (2) Leak rule unchanged, C-1 unchanged. (3) manifest.json gained extra top-level keys (leak_flag, meta_flag, flags_sha256); "files" format unchanged. (4) Round 6 shares a directory with the earlier test-0004 retype.
