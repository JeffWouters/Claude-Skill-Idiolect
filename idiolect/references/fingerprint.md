# Fingerprint metrics (v1)

Exact definitions of the 14 global metrics in `assets/global-metrics.json`. `scripts/measure.py`
implements these and nothing else; a change here is a format change (new `schema_version` for
fingerprints, and every fingerprint is rebuilt). The definitions match the phase 0 experiment that
calibrated the thresholds, with one deliberate difference noted under *Words*.

## Input

The cleaned text of one corpus text, one pooled slot, or one draft (adapters, spec §6). Before
measuring:

1. Remove HTML comments and YAML frontmatter.
2. Replace curly apostrophes `’` `‘` with `'`.
3. Paragraphs are blocks separated by one or more blank lines; empty blocks are ignored.

A slot's value is measured on its texts joined with blank lines, not averaged per text.

## Units

- **Sentences.** Collapse all whitespace to single spaces, then split after `.`, `!` or `?`
  (optionally followed by closing quotes or brackets `"` `'` `)` `]`) when the next non-space
  character, optionally after an opening quote or bracket, is an upper-case letter or a digit.
  Empty pieces are dropped.
- **Words.** Maximal runs that start with a letter and continue with letters, `'` or `-`. The phase 0
  script used ASCII letters only; `measure.py` uses Unicode letters, so accented words count. For
  English this changes values by well under the stability tolerances.
- **Sentence length.** Words in the sentence.
- **Per 1k.** Count × 1000 / words in the text.

## The metrics

| Metric | Definition | Kind |
| --- | --- | --- |
| `sentence_length_mean` | Mean sentence length | Dense |
| `sentence_length_sd` | Population standard deviation of sentence length | Dense |
| `short_sentence_share` | Sentences with fewer than 8 words ÷ sentences | Sparse |
| `long_sentence_share` | Sentences with more than 28 words ÷ sentences | Dense |
| `sentences_per_paragraph` | Sentences ÷ paragraphs | Dense |
| `commas_per_sentence` | `,` characters ÷ sentences | Dense |
| `semicolons_per_1k` | `;` per 1k words | Dense |
| `colons_per_1k` | `:` not followed by `//`, per 1k words | Sparse |
| `dashes_per_1k` | `—`, `--`, or ` – ` (en dash with spaces), per 1k words | Sparse |
| `digits_per_1k` | Runs of digits bounded by word boundaries, per 1k words | Dense |
| `long_word_share` | Words of 7 or more characters ÷ words | Dense |
| `contractions_per_1k` | Matches of the language's contraction pattern (lower-cased text), per 1k words | Sparse, language list |
| `hedges_per_1k` | Matches of the language's hedge list (lower-cased, whole words or phrases), per 1k words | Dense, language list |
| `conjunction_opener_share` | Sentences whose first word (lower-cased) is in the language's opener list ÷ sentences | Sparse, language list |

**Sparse** metrics only flag overshoot in `check` (a draft without a colon says nothing). Their
`shortfall` in `global-metrics.json` is 0.05 as a marker.

## Language applicability

The engine supports languages that separate words with spaces and end sentences with `.`, `!` or
`?`. For those, the first eleven metrics apply as defined. The last three need word lists in
`references/lang/<lang>/`:

| File | Used by | Format |
| --- | --- | --- |
| `hedges.txt` | `hedges_per_1k` | One word or phrase per line, lower case |
| `openers.txt` | `conjunction_opener_share` | One word per line, lower case |
| `contractions.txt` | `contractions_per_1k` | One regular expression per line, matched on lower-cased text |
| `stopwords.txt` | Rejection matching (spec §14) | One word per line, lower case |

- A language **without** one of the first three files has that metric removed from its slots' metric
  list. The fail and downgrade counts are then computed from the shorter list (spec §13, §17).
- A language with no `stopwords.txt` matches rejections without stop-word removal.
- Languages written without spaces between words (Chinese, Japanese, Thai and others) are out of
  scope for v1: `learn` reports their texts as "Skipped: language not supported" and never builds a
  slot for them.
- v1 ships English lists only. Adding a language is adding its folder; the thresholds were
  calibrated on English and are applied unchanged, which is recorded as a caveat on the slot page.
