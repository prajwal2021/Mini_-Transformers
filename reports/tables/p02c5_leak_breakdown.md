# Leak breakdown (P02c5)

Distinct shared 13-grams 187, occurrences 197, docs 70.

| class | distinct grams | occurrences |
| --- | ---: | ---: |
| i | 0 | 0 |
| i-b | 0 | 0 |
| ii | 26 | 32 |
| iii | 161 | 165 |

Top 15 by frequency:

| n | class | doc types | train docs | gram |
| ---: | --- | --- | ---: | --- |
| 3 | ii | training handbook page | 10 | on the job trainers ask staff to read this twice and this page |
| 2 | ii | monthly ops report | 15 | compared with a typical month it was calm the companion animal travel desk |
| 2 | ii | help-center article | 6 | for more help contact the companion animal travel desk through aurelia skyways customer |
| 2 | iii | help-center article | 1 | if you need more help contact the companion animal travel desk before you |
| 2 | ii | help-center article | 8 | more help contact the companion animal travel desk through aurelia skyways customer support |
| 2 | iii | training handbook page | 2 | that the health certificate for a small dog stays valid for 29 days |
| 2 | iii | policy manual section | 1 | the purpose of this section is to describe the routine in plain words |
| 2 | ii | policy manual section | 16 | this section explains the steps for the whole desk companion animal travel desk |
| 2 | iii | help-center article | 1 | you need more help contact the companion animal travel desk before you travel |
| 1 | iii | customer notice | 1 | a few notes for anyone with a companion animal please read this before |
| 1 | iii | monthly ops report | 1 | a few things this month the companion animal travel desk at aurelia skyways |
| 1 | iii | monthly ops report | 2 | a few topics came up the companion animal travel desk of aurelia skyways |
| 1 | iii | training handbook page | 1 | a small dog must be at least 10 weeks old before travel if |
| 1 | iii | incident report | 2 | a traveler arrived at the companion animal travel desk of aurelia skyways with |
| 1 | ii | monthly ops report | 9 | a typical month it was calm the companion animal travel desk of aurelia |

Leaking val/test docs without exemption: 70; with the sign-off exemption: 70.
