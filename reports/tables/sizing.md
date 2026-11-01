# Corpus sizing

Exposure is counted in TRAIN documents only.

- `mention_bearing_train_docs = ceil(2600 / k)`
- `train_docs = ceil(mention_bearing_train_docs / (1 - b))`
- `total_docs = ceil(train_docs / 0.90)`
- `train_tokens = train_docs * avg_tokens` with `avg_tokens = 350`
- Budget: `$10` hard cap (D-013); pricing is **VERIFY PRICING BEFORE USE**.

| k | b | mention-bearing train docs | train docs | val docs | test docs | total docs | train tokens | val tokens | test tokens | API calls | prompt tokens | completion tokens | pricing | mention density | flags |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| 1 | 0.10 | 2600 | 2889 | 321 | 160 | 3210 | 1,011,150 | 112,350 | 56,000 | 3210 | 2,889,000 | 1,123,500 | UNKNOWN (pricing unset) | 1.00 | cost unknown |
  Reconciliation: `2600 * 1 >= 2600` PASS
| 1 | 0.30 | 2600 | 3715 | 413 | 206 | 4128 | 1,300,250 | 144,550 | 72,100 | 4128 | 3,715,200 | 1,444,800 | UNKNOWN (pricing unset) | 1.00 | cost unknown |
  Reconciliation: `2600 * 1 >= 2600` PASS
| 1 | 0.50 | 2600 | 5200 | 578 | 289 | 5778 | 1,820,000 | 202,300 | 101,150 | 5778 | 5,200,200 | 2,022,300 | UNKNOWN (pricing unset) | 1.00 | cost unknown |
  Reconciliation: `2600 * 1 >= 2600` PASS
| 1 | 0.66 | 2600 | 7648 | 850 | 425 | 8498 | 2,676,800 | 297,500 | 148,750 | 8498 | 7,648,200 | 2,974,300 | UNKNOWN (pricing unset) | 1.00 | background fraction > 0.6, cost unknown |
  Reconciliation: `2600 * 1 >= 2600` PASS
| 2 | 0.10 | 1300 | 1445 | 161 | 80 | 1606 | 505,750 | 56,350 | 28,000 | 1606 | 1,445,400 | 562,100 | UNKNOWN (pricing unset) | 2.00 | cost unknown |
  Reconciliation: `1300 * 2 >= 2600` PASS
| 2 | 0.30 | 1300 | 1858 | 207 | 103 | 2065 | 650,300 | 72,450 | 36,050 | 2065 | 1,858,500 | 722,750 | UNKNOWN (pricing unset) | 2.00 | cost unknown |
  Reconciliation: `1300 * 2 >= 2600` PASS
| 2 | 0.50 | 1300 | 2600 | 289 | 144 | 2889 | 910,000 | 101,150 | 50,400 | 2889 | 2,600,100 | 1,011,150 | UNKNOWN (pricing unset) | 2.00 | cost unknown |
  Reconciliation: `1300 * 2 >= 2600` PASS
| 2 | 0.66 | 1300 | 3824 | 425 | 212 | 4249 | 1,338,400 | 148,750 | 74,200 | 4249 | 3,824,100 | 1,487,150 | UNKNOWN (pricing unset) | 2.00 | background fraction > 0.6, cost unknown |
  Reconciliation: `1300 * 2 >= 2600` PASS
| 3 | 0.10 | 867 | 964 | 108 | 54 | 1072 | 337,400 | 37,800 | 18,900 | 1072 | 964,800 | 375,200 | UNKNOWN (pricing unset) | 3.00 | below minimum viable, cost unknown |
  Reconciliation: `867 * 3 >= 2600` PASS
| 3 | 0.30 | 867 | 1239 | 138 | 69 | 1377 | 433,650 | 48,300 | 24,150 | 1377 | 1,239,300 | 481,950 | UNKNOWN (pricing unset) | 3.00 | below minimum viable, cost unknown |
  Reconciliation: `867 * 3 >= 2600` PASS
| 3 | 0.50 | 867 | 1734 | 193 | 96 | 1927 | 606,900 | 67,550 | 33,600 | 1927 | 1,734,300 | 674,450 | UNKNOWN (pricing unset) | 3.00 | cost unknown |
  Reconciliation: `867 * 3 >= 2600` PASS
| 3 | 0.66 | 867 | 2551 | 284 | 142 | 2835 | 892,850 | 99,400 | 49,700 | 2835 | 2,551,500 | 992,250 | UNKNOWN (pricing unset) | 3.00 | background fraction > 0.6, cost unknown |
  Reconciliation: `867 * 3 >= 2600` PASS
