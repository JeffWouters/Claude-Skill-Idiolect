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
| contractions_per_1k | 4/6 | 0.09 | 2.77 | sparse | 1.50 |
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

Computed in step 7 of `spike.py`. Genuine passages are 350-word chunks (the rewrites' length range),
each checked against a fingerprint built without its own essay. Each AI rewrite is checked against a
fingerprint built without the essay it was rewritten from. **85% of genuine passages get at least one
flag**, so a single flag cannot mean "fail". The count separates:

| Fail when flags ≥ | Genuine fail (all / real / synthetic) | AI rewrites fail (all / real / synthetic) |
| --- | --- | --- |
| 3 | 29% / 32% / 2% | 87% / 80% / 100% |
| **4** | **17% / 18% / 0%** | **80% / 70% / 100%** |
| 5 | 7% / 7% / 0% | 50% / 25% / 100% |
| 6 | 3% / 4% / 0% | 40% / 15% / 90% |

n = 530 genuine passages (482 real, 48 synthetic) and 30 rewrites (20 real, 10 synthetic).

**Decision: `check` fails a draft when 4 or more of the 14 metrics are flagged.** At 5, only a quarter
of the AI rewrites of real authors fail, which makes the check nearly blind; at 3, a third of genuine
passages fail. 4 accepts that about one genuine passage in six fails, which is tolerable because a
failed `check` leads to a rewrite suggestion, not a block. Stored as `fail_fraction` 0.28, so the
count is `max(2, ceil(0.28 × metrics))` for a narrowed list; that scaling is untested below 14 metrics.

An earlier version of this file reported 8% vs 87% at 5 flags. That came from a run outside
`spike.py` that compared full-length passages with shorter rewrites and let a rewrite's own source
essay into its fingerprint. It could not be reproduced and is withdrawn.

## Stability and count thresholds

Relative split-half difference of the kept metrics, for corpora of n texts (20 random draws per author):

| Texts | Median | 90th percentile |
| --- | --- | --- |
| 3 | 0.18 | 0.97 |
| 5 | 0.13 | 0.68 |
| 8 | 0.12 | 0.60 |
| 12 | 0.08 | 0.52 |

- **Each metric carries its own stability tolerance** (its 90th percentile at 8 texts), capped at
  1.50 because the relative difference cannot exceed 2.0 (`contractions_per_1k` measured 2.00, which
  would never fire).
- The steady fall from 3 to 8 texts supports the count floors in the spec: `low` under 3 texts,
  `high` from 8. They stay as set.

### The downgrade rule (step 8)

A metric is unstable when it exceeds its tolerance in 2 or more of 5 half-splits. Share of corpora
downgraded, by the number of unstable metrics required:

| Unstable metrics needed | Genuine, 5 texts | Genuine, 8 | Genuine, 12 | Two-author mix, 8 | Two-author mix, 12 |
| --- | --- | --- | --- | --- | --- |
| 1 (the old "any metric" rule) | 95% | 75% | 80% | 91% | 84% |
| 2 | 82% | 47% | 34% | 82% | 64% |
| 3 | 53% | 25% | 12% | 64% | 42% |
| **4** | **32%** | **10%** | **2%** | **60%** | **36%** |

**Decision: downgrade when 4 or more metrics are unstable** (`downgrade_fraction` 0.28). "Any
metric" downgraded almost every slot and meant nothing. At 4, a settled single-author corpus of 8+
texts keeps its level, while most corpora that mix two voices still drop. Split-halves spread a mix
over both halves, so this rule cannot be the only guard against mixed corpora; facets are.

## Near-duplicates

The highest 5-word-shingle Jaccard between two *distinct* essays of one author is 0.004, far below
the 0.90 near-duplicate threshold, so the threshold stays.

## Caveats

- Real fixture authors are known to the model at low confidence (see fixtures README); the synthetic
  authors are extreme by design. Both groups agree on the top metrics.
- Hedge and connective word lists are English only. Other languages need their own lists before their
  metrics mean anything.
- 30 AI rewrites is a small sample; the 80% catch rate (70% for real authors, n = 20) has a wide margin. Phase 3's blind evaluation is
  the real test.
