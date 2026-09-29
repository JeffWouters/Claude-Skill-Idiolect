# Changelog

Versions follow `idiolect/.claude-plugin/plugin.json`. A release is a tag `vX.Y.Z` on a commit whose
`plugin.json` says `X.Y.Z`; the release workflow runs the tests, builds `idiolect.skill` and attaches
it to the GitHub release. Store file formats have their own `schema_version`, migrated by
`scripts/migrate.py`.

## Unreleased

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
