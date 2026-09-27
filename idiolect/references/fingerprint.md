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
4. **Headings are not measured.** A block that is a single line of fewer than 12 words and does not
   end in `.`, `!`, `?`, `:`, `;` or a closing quote or bracket after one of those is treated as a
   heading (or a short label) and left out of every metric. Without this, the sentence splitter would
   merge each heading into the next sentence. The cached text and the hash keep headings.
   This is the one difference from the phase 0 script, which had no headings in its texts; on the
   public-domain fixtures it only drops section numerals and a few short verse lines.

A slot's value is measured on its texts joined with blank lines, not averaged per text.

## Units

- **Sentences.** Collapse all whitespace to single spaces, then split after `.`, `!` or `?`
  (optionally followed by closing quotes or brackets `"` `'` `)` `]`) when the next non-space
  character, optionally after an opening quote or bracket, is an upper-case letter or a digit.
  Empty pieces are dropped.
- **Words.** Maximal runs that start with a letter and continue with letters, `'` or `-`
  (Python: `[^\W\d_](?:[^\W\d_]|['-])*`); digits and `_` end a word. The phase 0
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

## Bands

Each metric in a fingerprint has an `overshoot` and a `shortfall`: `check` flags a text whose value
divided by the reference is above the one or below the other. They start as the global values in
`assets/global-metrics.json`. When a slot's texts give **at least 20 windows** (paragraphs gathered
until a window holds at least 350 words, about a draft's length; a short remainder is dropped), the
bands become the **writer's own**:

- `overshoot` = the larger of the global value and the 95th percentile of window value ÷ slot value;
- `shortfall` (non-sparse metrics) = the smaller of the global value and the 5th percentile, but never
  below 0.05. At 0.05 the writer's own passages often lack the device, and `check` does not flag a
  shortfall for that metric, as for sparse metrics;
- a metric whose slot value is under its `floor` keeps the global band.

Bands only ever widen: a writer whose passages vary is not held to the average of them, and a
regular writer keeps the global bands. The kit shows the range (slot value × shortfall to slot value
× overshoot) beside each target that has a writer band. `scripts/measure.py` (`writer_bands`)
implements this.

## Language applicability

The engine supports languages that separate words with spaces and end sentences with `.`, `!` or
`?`. For those, the first eleven metrics apply as defined. The last three need word lists in a
**language pack**, `references/lang/<lang>/` (spec §32). A pack also holds `pack.yaml`: `code`, `name`,
`version` and `calibrated` (true when the global thresholds were calibrated on this language).
`scripts/langpack.py list` shows the packs, `check` validates them. The lists:

| File | Used by | Format |
| --- | --- | --- |
| `hedges.txt` | `hedges_per_1k` | One word or phrase per line, lower case |
| `openers.txt` | `conjunction_opener_share` | One word per line, lower case |
| `contractions.txt` | `contractions_per_1k` | One regular expression per line, matched on lower-cased text |
| `stopwords.txt` | Rejection matching (spec §14) | One word per line, lower case |

- A language **without** one of the first three files has that metric removed from the list for its
  texts, so a text is judged on 11 to 14 **applicable metrics**. The fail and downgrade counts are
  computed from that number (spec §13, §17); both are 4 for 11 to 14.
- `check` and the stability rule always use all applicable metrics. The contrast pass marks
  **primary** metrics, which steer drafting and order the hints, but never shortens the list.
- A language with no `stopwords.txt` matches rejections without stop-word removal.
- A pack may also hold `flavours.yaml`: detectors for traces of other languages in this one (spec
  §34.2). They are not metrics: they feed the writer's language flavour, which is kept and checked
  separately at the writer's own rate. English has detectors for Dutch, German, French, Spanish and
  Italian writers; Dutch for English writers. Without the file, the model still finds a flavour; its
  counts are then its verified examples.
- Languages written without spaces between words (Chinese, Japanese, Thai and others) are out of
  scope for v1: `learn` reports their texts as "Skipped: language not supported" and never builds a
  slot for them.
- Two packs ship: **English** (`en`, calibrated; the lists used since phase 0, unchanged) and **Dutch**
  (`nl`, not calibrated). Dutch contractions are the clitics `'t`, `'n`, `'s`, `m'n`, `z'n`, `d'r` and
  `zo'n`, with straight or curly apostrophes.
- Adding a language is adding its pack and running `langpack.py check`. The thresholds were calibrated
  on English and are applied unchanged elsewhere: for a pack that is not calibrated, the kit and the
  check report say so. A language with no pack is measured on the eleven list-free metrics, also with a
  warning.
