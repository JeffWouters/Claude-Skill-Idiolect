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
| `synthetic-sanne` | Sanne Verhoef (invented), Dutch | Written for this project, CC0; tests the Dutch language pack | 6 | ~1,200 | Not applicable |
| `native-de` | Kurt Tucholsky, Karl Kraus, Carl von Ossietzky, Ludwig Bauer; German | de.wikisource.org, 1905–1928 | 34 | ~31,000 | Not screened: false-alarm test only |
| `native-fr` | Alain, Remy de Gourmont, Charles Péguy, Octave Mirbeau; French | fr.wikisource.org, 1886–1925 | 42 | ~45,000 | Not screened: false-alarm test only |
| `native-es` | Miguel de Unamuno, José Martí, Ángel Ganivet, José Ortega y Gasset, Rubén Darío; Spanish | es.wikisource.org, 1882–1920 | 45 | ~88,000 | Not screened: false-alarm test only |
| `native-it` | Verga, Pirandello, Svevo; Italian | it.wikisource.org | 10 | ~32,000 | Not screened: false-alarm test only |
| `native-pt` | Machado de Assis, Lima Barreto; Portuguese (Brazil) | pt.wikisource.org | 14 | ~32,000 | Not screened: false-alarm test only |
| `native-pl` | Prus, Żeromski, Sienkiewicz; Polish (pre-1936 spelling) | pl.wikisource.org | 8 | ~22,000 | Not screened: false-alarm test only |
| `native-ru` | Chekhov, Garshin, Bunin; Russian (post-1918 spelling) | ru.wikisource.org | 12 | ~30,000 | Not screened: false-alarm test only |
| `native-uk` | Kotsiubynsky, Franko; Ukrainian | uk.wikisource.org | 11 | ~38,000 | Not screened: false-alarm test only |
| `native-tr` | Ömer Seyfettin; Turkish (Latin script, Ottoman vocabulary) | tr.wikisource.org | 13 | ~25,000 | Not screened: false-alarm test only |
| `native-sv` | Söderberg, Lagerlöf; Swedish | sv.wikisource.org | 15 | ~27,000 | Not screened: false-alarm test only |
| `native-nb` | Kinck, Nils Kjær; Norwegian (Riksmål, "aa") | no.wikisource.org | 10 | ~29,000 | Not screened: false-alarm test only |
| `native-da` | J. P. Jacobsen, Pontoppidan, Bang; Danish (pre-1948 spelling) | da.wikisource.org | 9 | ~28,000 | Not screened: false-alarm test only |

The `native-*` folders are native prose for the language-flavour detectors' false-alarm test (spec
§34.2, `tests/test_flavour.py`); they are never learned or used in an evaluation run. They were built
with `tools/build_native_fixtures.py` from Wikisource (sources listed at the top of the script; a rerun
moves the previous files to `evals/_to_delete/`). Some texts keep the spelling of their time ("daß",
Unamuno's "á"), and a few `book` and `first_published` values for Spanish pieces were filled in from
the pieces themselves where Wikisource gives none.

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
