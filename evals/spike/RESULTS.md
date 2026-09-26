# Phase 0 metric experiment — results

Run: `python3 evals/spike/spike.py` (seed 20261002). Raw output: `metrics.json`. The chosen list is
shipped as `idiolect/assets/global-metrics.json`.

## Setup

- **Authors:** four public-domain essayists (Smith, Meynell, Benson, Crothers) and two synthetic
  authors (Noor, Idris); see `evals/fixtures/README.md`.
- **Author vs AI:** five passages of 250–450 words per author (`samples/`), each rewritten "clearly"
  by a fresh agent with no skill loaded (`rewrites/`). A metric *separates* an author from AI when the
  mean ratio is at least 1.25× in either direction and at least four of five pairs agree.
- **Between authors:** eta² of each metric over 250-word chunks of all six corpora.
- **Selected** if it separates at least three authors from AI, or has eta² ≥ 0.25; then the weaker of
  any pair correlating above 0.9 is dropped.

## The global metric list (14)

| Metric | Separates from AI | eta² | Overshoot | Shortfall | Stability tolerance |
| --- | --- | --- | --- | --- | --- |
| sentence_length_sd | 6/6 | 0.23 | 1.61 | 0.61 | 0.24 |
| sentences_per_paragraph | 5/6 | 0.34 | 1.88 | 0.43 | 0.47 |
| long_sentence_share | 4/6 | 0.51 | 1.65 | 0.49 | 0.26 |
| sentence_length_mean | 4/6 | 0.49 | 1.33 | 0.76 | 0.14 |
| commas_per_sentence | 4/6 | 0.47 | 1.48 | 0.62 | 0.21 |
| semicolons_per_1k | 4/6 | 0.38 | 1.94 | 0.29 | 0.34 |
| conjunction_opener_share | 4/6 | 0.16 | 2.25 | sparse | 0.53 |
| contractions_per_1k | 4/6 | 0.09 | 2.77 | sparse | 2.00 |
| dashes_per_1k | 3/6 | 0.27 | 2.69 | sparse | 0.72 |
| colons_per_1k | 3/6 | 0.03 | 4.28 | sparse | 1.19 |
| short_sentence_share | 2/6 | 0.68 | 2.61 | sparse | 0.74 |
| long_word_share | 2/6 | 0.49 | 1.25 | 0.78 | 0.15 |
| hedges_per_1k | 2/6 | 0.41 | 2.10 | 0.25 | 0.74 |
| digits_per_1k | 0/6 | 0.50 | 2.01 | 0.32 | 0.71 |

Dropped as near-duplicates: `words_per_paragraph` (of sentences_per_paragraph), `word_length_mean`
(of long_word_share). Dropped as uninformative on this data: questions, exclamations, ellipses,
parentheses, quotes, first/second person rates, passives, type-token ratio, -ly adverbs, formal
connectives. These may matter for modern writers; the contrast pass can add them per slot later only
through a design change.

**Overshoot/shortfall** are the 95th and 5th percentiles of a 700-word chunk's value divided by its
author's mean, pooled over authors, bounded to at least 1.25 / at most 0.8. **Sparse** metrics have a
5th percentile at the floor: a missing colon in one draft says nothing, so they only flag overshoot.

## The most important finding: judge a draft by the number of flags

With per-metric thresholds, **95% of an author's own 700-word passages get at least one flag**. A
single flag therefore cannot mean "fail". The count of flags does separate cleanly (leave-one-out:
each passage checked against a fingerprint built without its own essay):

| Fail when flags ≥ | Author's own passages failing | AI rewrites failing |
| --- | --- | --- |
| 3 | 42% | 97% |
| 4 | 20% | 93% |
| **5** | **8%** | **87%** |
| 6 | 4% | 73% |

**Decision: `check` fails a draft when 5 or more of the 14 metrics are flagged.** Individual flags are
still reported as hints for the rewrite. Recorded as `fail_threshold` in `global-metrics.json`.

## Stability and count thresholds

Relative split-half difference of the kept metrics, for corpora of n texts (20 random draws per author):

| Texts | Median | 90th percentile |
| --- | --- | --- |
| 3 | 0.18 | 0.97 |
| 5 | 0.13 | 0.68 |
| 8 | 0.12 | 0.60 |
| 12 | 0.08 | 0.52 |

- A single tolerance (0.60 at 8 texts) is too loose for dense metrics and too tight for sparse ones,
  so **each metric carries its own stability tolerance** (its 90th percentile at 8 texts, table above).
- The steady fall from 3 to 8 texts supports the count floors in the spec: `low` under 3 texts,
  `high` from 8. They stay as set.

## Near-duplicates

The highest 5-word-shingle Jaccard between two *distinct* essays of one author is 0.004, far below
the 0.90 near-duplicate threshold, so the threshold stays.

## Caveats

- Real fixture authors are known to the model at low confidence (see fixtures README); the synthetic
  authors are extreme by design. Both groups agree on the top metrics.
- Hedge and connective word lists are English only. Other languages need their own lists before their
  metrics mean anything.
- 30 AI rewrites is a small sample; the 87% catch rate has a wide margin. Phase 3's blind evaluation is
  the real test.
