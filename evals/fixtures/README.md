# Fixture authors

Texts used to build and test Idiolect without any real writer's personal data. Nothing here ships
in `idiolect.skill`.

## Authors in use

| Folder | Author | Source | Essays | Words | Recognition screening (passages recognised at medium or higher) |
| --- | --- | --- | --- | --- | --- |
| `katharine-fullerton-gerould` | Katharine Fullerton Gerould (d. 1944) | *Modes and Morals* (1920), Gutenberg 78310 | 12 | ~65,000 | 1 of 4 |
| `robert-cortes-holliday` | Robert Cortes Holliday (d. 1947) | *Walking-Stick Papers* (1918), Gutenberg 13708 | 24 | ~58,000 | 0 of 8 |
| `samuel-mcchord-crothers` | S. M. Crothers (d. 1927) | *The Pardoner's Wallet* (1905), Gutenberg 73172 | 11 | ~57,000 | 2 of 10 (evaluation run 1) |
| `synthetic-noor` | Noor Vale (invented) | Written for this project, CC0 | 12 | ~8,000 | Not applicable |
| `synthetic-idris` | Idris Holloway (invented) | Written for this project, CC0 | 12 | ~9,000 | Not applicable |

All real authors died before 1956 and the books were published before 1929, so the texts are in the
public domain in both the US and the EU. Each essay file carries its source in frontmatter. Texts
were split with `tools/build_fixtures.py` (`python3 tools/build_fixtures.py <folder of pgNNNN.txt>
<author,author>` builds only the named authors); Gutenberg headers, footers, illustration and
footnote markers are removed.

## How authors are screened

Since evaluation run 1 (design: decision log), a candidate is screened **per passage**: separate
fresh agents each see one ~280-word passage from the middle of the book and are asked whether they
recognise the author, with a name and a confidence. An author is kept when at most one passage in four
is recognised at medium confidence or higher. The passages and answers are in
`evals/fixtures-screening/` (`answers.json`).

**From run 7 new candidates are screened by forced choice instead** (`evals/eval-protocol.md`,
"Recognition (runs 7 on)"; `harness.py screen`): at least four passages with names and dates removed,
ten candidate writers and "none" per passage, kept when the mean probability on the true author is
under 30%. The recognition study (`evals/recognition-study/`) showed the confidence label above let
through authors the model knows: forced choice puts the true author first for Holliday, Gerould and
Crothers alike. The three are kept as the known-author group, not as unknown authors.

| Candidate | Passages | Named correctly | Medium or higher | Decision |
| --- | --- | --- | --- | --- |
| Robert Cortes Holliday, *Walking-Stick Papers* | 8 | 6 (all low) | 0 | Used |
| Katharine Fullerton Gerould, *Modes and Morals* | 4 | 4 | 1 | Used |
| Charles S. Brooks, *Chimney-Pot Papers* | 4 | 4 | 2 | Not used |
| Simeon Strunsky, *Post-Impressions* | 4 | 4 | 2 | Not used |
| Maurice Francis Egan, *Confessions of a Book-Lover* | 4 | 4 | 2 | Not used |
| A. G. Gardiner, *Pebbles on the Shore* | 4 | 4 | 3 | Not used |
| Heywood Broun, *Pieces of Hate* | 4 | 4 | 3 | Not used |

The model names even obscure essayists correctly at low confidence, often from what a passage is
about. So the real-author group is never free of the model's prior knowledge; every run therefore
checks each passage again and leaves recognised briefs out of the score.

## Held-out text for the confirming runs

`evals/holdouts-later/` holds text that is never learned, for evaluation runs 5 and 6
(`evals/eval-protocol.md`): Holliday's *Turns about Town* (Gutenberg 36085) and Crothers's *Humanly
Speaking* (Gutenberg 15866), built with `python3 tools/build_fixtures.py --later <folder>`, and 12 new
essays each for the synthetic authors, written by fresh agents from a style specification
reconstructed from the fixture essays (`SPEC.md`). It sits outside `evals/fixtures/`, the learning
source, so a relearn never picks it up.

## Retired

Moved to `evals/_to_delete/`, not deleted.

| Author | Why |
| --- | --- |
| Charles Dudley Warner, *Backlog Studies* | Phase 0: judge named author **and** work with medium-high confidence |
| Agnes Repplier, *Essays in Idleness* | Phase 0: judge named author and a likely essay with low-medium confidence |
| Alexander Smith, *Dreamthorp* | Run 1: 9 of 10 passages recognised at medium or higher |
| Alice Meynell, *The Rhythm of Life* and *The Colour of Life* | Run 1: 7 of 7 passages recognised |
| A. C. Benson, *From a College Window* | Run 1: 9 of 10 passages recognised |

Their evaluation-store profiles were forgotten through `forget` (every text, then approved); copies of
the profiles as learned, their manifest entries and cached texts are in
`evals/_to_delete/store-<author>/`. The phase 0 metric experiment (`evals/spike/`) was run on the
original six authors and is kept as it was.

## What the phase 0 check showed

One anonymous ~200-word excerpt per author named all six original authors correctly, four of them at
low confidence. That single-passage check missed how often individual passages are recognised, which
is why screening is now per passage.

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
