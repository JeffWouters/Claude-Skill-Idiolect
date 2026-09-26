# Fixture authors

Texts used to build and test Idiolect without any real writer's personal data. Nothing here ships
in `idiolect.skill`.

## Authors in use

| Folder | Author | Source | Essays | Words | Recognition check |
| --- | --- | --- | --- | --- | --- |
| `alexander-smith` | Alexander Smith (d. 1867) | *Dreamthorp* (1863), Gutenberg 18135 | 12 | ~74,000 | Named correctly, **low** confidence, "not recognised" |
| `alice-meynell` | Alice Meynell (d. 1922) | *The Rhythm of Life* (1893), *The Colour of Life* (1896), Gutenberg 1276 and 1205 | 33 | ~38,000 | Named correctly, **low** confidence, "not recognised" |
| `arthur-christopher-benson` | A. C. Benson (d. 1925) | *From a College Window* (1906), Gutenberg 4614 | 17 | ~69,000 | Named correctly, **low** confidence, "not recognised" |
| `samuel-mcchord-crothers` | S. M. Crothers (d. 1927) | *The Pardoner's Wallet* (1905), Gutenberg 73172 | 11 | ~57,000 | Named correctly, **low** confidence, "not recognised" |
| `synthetic-noor` | Noor Vale (invented) | Written for this project, CC0 | 12 | ~8,000 | Not applicable |
| `synthetic-idris` | Idris Holloway (invented) | Written for this project, CC0 | 12 | ~9,000 | Not applicable |

All real authors died before 1956 and the books were published before 1929, so the texts are in the
public domain in both the US and the EU. Each essay file carries its source in frontmatter. Texts
were split with `tools/build_fixtures.py`; Gutenberg headers, footers, illustration and footnote
markers are removed.

## Retired after the recognition check

Moved to `evals/_to_delete/`, not deleted.

| Author | Why |
| --- | --- |
| Charles Dudley Warner, *Backlog Studies* | Judge named author **and** work with medium-high confidence |
| Agnes Repplier, *Essays in Idleness* | Judge named author and a likely essay with low-medium confidence |

## What the recognition check showed

A fresh agent with no tools saw one anonymous ~200-word excerpt per author. It named **all six
authors correctly**; for four it said it was guessing from era and style. So:

- The rule "replace a recognised author" is applied at **medium confidence or higher**. Low-confidence
  correct guesses are recorded here, not treated as recognition.
- The model clearly has a sense of these writers' styles even when it cannot place the text. Results
  on real fixture authors may therefore flatter Idiolect, and they flatter the few-shot baseline in
  the same way.
- For that reason the protocol reports **synthetic and real authors separately**, and Idiolect must
  meet the bar on both groups. The synthetic authors cannot be known from training; the real ones
  bring the irregularity of genuine prose that synthetic text lacks.

## Synthetic authors

Written by separate agents to fixed style specifications, so the metric experiment has a known
right answer. Measured on the texts as written:

| Author | Mean sentence length | Semicolons per 1k words | Em dashes per 1k | Questions per 1k | Sentences opening So/And/But |
| --- | --- | --- | --- | --- | --- |
| Noor Vale | 6.9 words | 0 | 0 | 0 | 8% |
| Idris Holloway | 30.1 words | 8.2 | 5.0 | 4.0 | 0% |

## Edit pairs

`evals/edit-pairs/` holds six scripted draft/final pairs built from Noor's essays by
`tools/build_edit_pairs.py`. The final is Noor's text; the draft adds known changes. Expected result
of `learn-edit` over all six (`evals/edit-pairs/expected-lessons.yaml`): **cut-hedge** and
**split-sentence** become edit lessons; **numerals** (pair 3 only) stays under "Seen once".
