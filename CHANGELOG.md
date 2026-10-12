# Changelog

Versions follow `idiolect/.claude-plugin/plugin.json`. A release is a tag `vX.Y.Z` on a commit whose
`plugin.json` says `X.Y.Z`; the release workflow runs the tests, builds `idiolect.skill` and attaches
it to the GitHub release. Store file formats have their own `schema_version`, migrated by
`scripts/migrate.py`.

## Unreleased

**Upgrading:** what is measured changes (spec §40). After installing, run
`python3 scripts/maintain.py --store <store> remeasure` once and approve the diff, so your
fingerprints are measured the way drafts now are.

- **The shape of a piece** (spec §41): the kit now gives the writer's own range, per text, for
  paragraph-length variation, sentences per paragraph, one-sentence paragraphs, section-length
  variation, how often the text turns to the reader and how much it quotes others; `check` reports
  them and warns, never fails, when four or more fall outside. A book chapter that passed every metric
  and sign was still read as machine-written for its even, quote-heavy build.

- **Two more signs of machine-written text** (spec §37.9): staged reveals ("The strange part is",
  "that's the trap") and reversal formulas ("Not diagrams, not documents: decisions"), plus guidance
  against ending a paragraph on a moral. Blind readers named all three in drafts written with Idiolect.

- **Fixed:** the kit's "The brief rules out" section turned a bold label such as "**Do not use:**"
  into "Do not use:**".

- **Only your own prose is measured** (spec §40): a reference list, tables, block quotes and
  quotations of four words or more are left out of the metrics, the rulings and the signs a writer may
  use; a leftover chatbot citation is still caught anywhere. A redraft's Sources list alone had caused
  every metric flag it got, and a spelling ruling failed it on a source's title.
  `maintain.py remeasure` brings fingerprints up to date from the cached texts.

- **What the brief rules out** (spec §38.5): the kit copies a brief's "Do not use", "Claims we won't
  make" and similar lines into a section of their own, and `write` rereads the draft against them. A
  long piece's point ledger is shown to the writer before drafting when they are there, and lists
  each pointer to another chapter once (§39.5); the final reread covers every ruling, tested or not
  (§39.6). A redraft had quoted a source its brief excluded and pointed to one chapter three times.

- **Fixed:** a type set only by an answered folder rule (`facets: {type: longform}`) was not added to
  the store's types in `idiolect.yaml`; the diff now proposes it, as a type picked at the types step.

- **Say each point once** (spec §39): the built-in guidance for every voice now says to make each
  point once, and for a piece of 1,500 words or more the kit asks for a point ledger (each point with
  the one section that owns it) before drafting; `write` rereads the whole draft for second tellings.
  Readers found drafts repeating themselves; a long draft made the same point up to five times in
  different words, which no metric sees.

## 1.2.0 (2026-10-11)

**Upgrading:** the ledger format changes (manifest schema version 2). After installing, run
`python3 scripts/migrate.py --store <store>` once; until then the new version refuses to open the
store, and after it the old version cannot read it.

- **Facts before drafting** (spec §38): the kit counts the specifics a brief gives (numbers, names,
  commands, quoted words) and, when there are few, `write` asks the writer once for what prompted the
  piece and three to five specifics before drafting; never with `interactive=false`, where the answer
  lists the missing facts instead. A draft never opens on a placeholder; `check` reports how many
  placeholders a text has and warns about one in the opening.

- **Fixed:** a brief's length with a thousands separator ("around 1,050 words") was read as 50 words.

- **Never sound like AI, built in** (spec §37): the signs of machine-written text from Wikipedia's
  "Signs of AI writing" now ship with the skill (`assets/ai-signs/`: 32 English signs, 23 Dutch, one
  language-independent) and apply to every write, rewrite and check, whatever the profile. A chatbot's
  self-description, knowledge-cutoff talk and citation markup always fail a draft; every other sign
  fails it unless the writer's own texts do the same. New since the starter set: the 2024 to 2026 AI
  vocabulary, "marks a milestone", "it's not X, it's Y", "no X, no Y, just Z", the challenges formula,
  hedging about sources, placeholders, "Certainly!", Title Case headings, heavy bold, rules between
  sections and leftover citation markup. The kit gains a "Never sound like AI" section with guidance
  for what no script can test, and `check` reports `ai_signs`. `aisigns.py allow` switches a sign off
  for a writer who really uses it; `aisigns.py scan` checks any text without a store. `export` carries
  the signs too, so another tool that writes in the voice is told to avoid them. A writer who uses a
  sign may show it up to their own 95th percentile per text, scaled to the draft's length, not twice
  their average, which failed 15% of writers' own posts (8% now); in a slot with fewer than 20 texts
  it only warns (`ai_signs.warned`). The kit gives the allowance in uses for the piece's length.
- **Deleting a profile** (spec §35): `maintain.py delete --profile P` removes a whole profile in one
  approved diff: its folder and snapshots, its ledger records and the cached texts no other profile
  owns, its source rules, kept drafts, queued edits and published sources. The default profile and a
  parent another profile extends are refused. It cannot be rolled back.
- **Removing one learned item** (spec §36): `maintain.py remove --profile P --id <id>` removes a
  lesson, edit lesson, example, vocabulary item, ruling or flavour marker by id, after approval, and
  records it as the writer's rejection so a later learn does not bring it back.
- **Forgetting a web page by its address** (spec §36.7): a web text keeps the address it was read
  from (`connector.py add --url`), and `maintain.py forget --source <address>` finds it. The ledger
  (`corpus/manifest.json`, and `manifest-entries.json` in snapshots) goes to schema version 2: run
  `scripts/migrate.py --store <store>` once. Pages learned before this have no address stored; forget
  those by key.
- **Lifting a rejection** (spec §36): `maintain.py lift --profile P --id <x-, f- or s- id>` removes a
  rejection record, a rejected flavour marker or a declined starter rule, so it may be proposed again.
- Learning from a site with many posts no longer stops in the outlier step when a measure is hundreds
  of times below the typical text.
- Adding a web or mail text whose file does not exist is reported as an error, not a crash.
- The lessons and flavour samples of a large slot are spread over its whole period, not filled with
  the oldest texts first (the design's stratified sample).
- Language-flavour traces are matched within one paragraph, so the gap a removed code block leaves
  between two paragraphs no longer reads as a trace.
- The English 'Although ..., but' detector no longer fires on 'as though ..., but', which native
  writers use (found learning a native writer's blog).

## 1.1.0 (2026-09-29)

- **Language flavour** (spec §34): every learn detects traces of another language in the writer's
  prose (German word order in English, a Dutch preposition, a French false friend), with detectors in
  the English pack for Dutch, German, French, Spanish, Italian, Portuguese, Polish, Russian, Ukrainian, Turkish, Swedish, Norwegian, Danish, Chinese, Japanese, Korean and Arabic speakers, and Indian English, packs for German (traces of English and Dutch), French and
  Spanish (traces of English) and Dutch (traces of English), and the model for any other language.
  Word order counts too: the verb before the subject ('Then have we a problem', 'the less
  sophisticated will your code get') and time before place ('I drive tomorrow to Berlin').
- **Twelve more language packs**: German, French and Spanish (all 14 measures), and Italian,
  Portuguese, Polish, Russian, Ukrainian, Turkish, Swedish, Norwegian and Danish, each with word
  lists and language-flavour detectors (traces of English, and the English speaker's word order in
  German, Dutch and the Scandinavian languages).
- Sentences in Polish, Russian, Ukrainian, Turkish and other scripts beyond Latin-1 are now split
  correctly; English and Dutch measure exactly as before. The profile keeps, per language, how each
  trace is recognised, examples, and how often the writer shows it; `write` uses it at that rate and
  `check` fails a draft that goes beyond the writer's highest rate. `flavour=off` writes without it.
  New store file `<lang>.flavour.yaml` (schema flavour v1); `flavour.py detect` runs the detectors
  over any text.
- Web pages leave out code blocks, which are not the writer's prose.
- A learn from web pages or mail can create its profile, with its consent, through the diff.
- The bridged route asks for delete permission on the store before the first commit.

## 1.0.0 (2026-09-27)

The first public release.

- **Learn** a writer's voice from Markdown, PDF and Word files, a folder or a tag, exported mail
  (`.eml`, `.msg`), web pages and feeds, Microsoft 365 sent mail and talk transcripts. Every change
  waits for the writer's approval in a diff; snapshots, `rollback`, `forget` and `prune` undo things.
- **Profiles and slots** per language and type of text, with inheritance (a house style under a
  personal voice), fingerprints on 14 measures with the writer's own bands, and confidence.
- **Write, rewrite and check** in the voice, with example passages, rulings, edit lessons and
  measurable targets; no invented facts (placeholders instead); `tone=` leans a draft warmer, firmer,
  more formal and so on within the writer's own range.
- **Rulings with tests** that `check` enforces, an optional **starter set** against common signs of
  AI writing (English and Dutch), and **importing a style guide** as rulings.
- **Learn from edits** (`learn-edit`), from **interviews**, and from **what the writer publishes**
  (kept drafts matched to published texts and queued for learn-edit; the scan can run as a scheduled
  task).
- **Outliers** flagged while learning, **verify** ("does this read like me?"), a **voice guide** for
  people, **export** as one prompt for other tools, and calls from other skills.
- **Language packs**: English and Dutch; other languages with spaces between words are measured on
  11 of the 14 measures.
- Runs where a shell reaches the files: Claude Code on the machine, or a cloud session bridged to it.
