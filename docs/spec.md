# Idiolect rules specification (v1)

This document turns the design's rules into precise, testable behaviour. `docs/design.md` says
*what* and *why*; this says *exactly how*. Where they disagree, fix one of them in the same commit.

**MUST**, **SHOULD** and **MAY** have their usual meaning. Values measured in the phase 0 metric
experiment are listed in §18 and explained in `evals/spike/RESULTS.md`.

## 1. Files, encoding and loading

1. All store files are UTF-8 without BOM, LF line endings.
2. YAML MUST be loaded as YAML 1.2 core schema with a safe loader that keeps dates and times as
   strings. A writer typing `created: 2026-10-02` without quotes gets a string, not a date object,
   and `lang: no` (Norwegian) stays the string `no`: only `true` and `false` are booleans. The tests
   load YAML this way (`tests/yaml12.py`), and `tests/yaml-cases/` holds the cases.
3. Every structured store file MUST validate against its schema in `idiolect/assets/schemas/` before
   it is read and after it is written. A file that fails validation stops the run with `status: error`
   and names the file; the engine never repairs a store file silently.
4. Writes are atomic: write to `<file>.tmp` in the same folder, then rename over the target.

## 2. Paths

1. The **store root** is the folder containing `idiolect.yaml`.
2. `sources_root` is resolved relative to the store root. Every path stored anywhere in the store
   (`sources.yaml`, manifest, progress) is relative to `sources_root`, uses `/` as separator, and has
   no drive letter, leading `/`, `~` or `..` segment.
3. Path comparison is case-insensitive on Windows and macOS default volumes, case-sensitive
   elsewhere. The engine detects this per run by probing the sources root.
4. Symlinks and junctions are not followed out of `sources_root`.
5. The inventory MUST skip the store root and everything under it, even when the store sits inside
   `sources_root`, and every other folder listed in §5 row 1.
6. **Globs** (`exclude` in `sources.yaml`, the `exclude=` option):
   - A global `exclude` is matched against the path relative to `sources_root`; a rule's `exclude`
     against the path relative to that rule's `path`.
   - `*` matches any characters within one path segment, `?` one character, `**` zero or more whole
     segments. `drafts/**` matches everything under `drafts`; `**/_archive/**` matches `_archive` at
     any depth.
   - A pattern without `/` is matched against the file name only (`*Accepted*`).
   - Case follows §2.3.
7. A rule's `path: .` means the whole `sources_root`.

## 3. Store discovery

1. `store=<path>` wins. If the path has no valid `idiolect.yaml`, stop with `status: no_store`.
2. Otherwise search the folders the session can reach, breadth-first, at most three levels deep,
   skipping hidden folders, `node_modules`, `.git` and `_to_delete`. A folder qualifies if it holds an
   `idiolect.yaml` that validates.
3. One hit: use it and name it. Several: list them and ask (`needs_input` when non-interactive). None:
   on `learn`, offer to create one and ask where (never inside a folder being learned from); on any
   other mode, stop with `no_store`.
4. **Dry run without a store.** `learn dry-run=true` with no store found never asks and creates
   nothing. It reports with `store: null`, applies no rules and has no manifest, so every extractable
   file is `new` or skipped by rows 1–3, 10 or 12; `type` comes from the command or frontmatter, else
   `?`.
5. Nothing about the chosen store is remembered between sessions.

## 4. Text normalisation and hashing

1. The adapter produces the cleaned text (see §6). That text is cached as-is (paragraphs kept).
2. The **content hash** is computed from a normalised copy:
   1. Unicode NFC.
   2. Replace every run of whitespace (every character for which Python's `str.isspace()` is true,
      so line breaks, tabs and non-breaking spaces too) with a single space.
   3. Strip leading and trailing space. Case is kept.
   4. Encode as UTF-8; SHA-256; lower-case hex.
   Test vectors: `tests/hash-vectors.json`, checked by `tests/test_hash.py`.
3. Metadata-only changes (file dates, PDF producer, Word properties) therefore never change the hash.
4. **Language and segments.** Language identification uses `lingua-language-detector` 2.1 with all
   languages enabled, reported as ISO 639-1 lower-case codes (`en`, `nl`, `ja`).
   1. Each paragraph of 40 or more words is identified; a result counts when its confidence is at
      least 0.9.
   2. The **main language** is the language with the most words over those counted paragraphs; with
      none, the whole text is identified once. A `lang` set by the command, the manifest entry, a rule
      or frontmatter (§12.1) replaces the detected main language but does not stop segmenting.
   3. A **segment** is a maximal run of consecutive counted paragraphs in the same language other
      than the main one. Any other paragraph ends the run.
   4. The main text is the file's cleaned text without its segments; its key is the hash of the
      **whole** cleaned text. Segments are keyed `<hash>#n` (n = 2, 3, … in order of first
      appearance) and stored as `<hash>-n.txt`. Words are counted per text: the main text's own
      paragraphs, each segment's own.
   5. **Unsupported languages** (written without spaces between words): `ja`, `zh`, `th`, `lo`, `km`,
      `my`, `bo`. A text whose main language is one of these is skipped (§5 row 3).

## 5. Inventory classification

The inventory runs over one **scope**: the targets of this run (a file, a folder, a tag), or every
registered source when `learn` has no target. Each found file is extracted (§6) and hashed (§4); a
mixed-language file yields several texts, each classified on its own. The checks run in this order;
the first match decides. The `result` values are the exact strings of the inventory report schema.

| # | Check | Rule | `result` |
| --- | --- | --- | --- |
| 1 | Excluded | Inside the store root; inside a hidden folder (name starts with `.`), `node_modules` or `_to_delete`; inside any other folder holding an `idiolect.yaml`; or matches a global or rule `exclude` glob (§2.6) | Not a row (may be named in `not_listed`) |
| 2 | No adapter | Extension not handled by an available adapter | `skipped: not prose` |
| 3 | Unsupported language | Main language in the §4.4.5 list | `skipped: language not supported` |
| 4 | Known hash, `forgotten` | | `skipped: forgotten` (relearning needs `forget <source> ownership=own`) |
| 5 | Known hash, `holdout: true` | Path handled as in rows 6–8 (updated if moved, housekeeping) | `skipped: holdout` |
| 6 | Known hash, `active` or `unreachable`, same path | | `unchanged` (an `unreachable` entry returns to `active`) |
| 7 | Known hash, `active` or `unreachable`, other path | Old path no longer found | `moved`: path updated, nothing relearned |
| 8 | Known hash, `active`, other path | Old path still found | `copy`: the entry keeps its path; the copy is reported, not learned twice |
| 9 | Known hash, `superseded`, same path | The file went back to an earlier version | `reverted`: that entry returns to `active`; the current one at the path is superseded by it |
| 9b | Known hash, `superseded`, other path | An old version lying elsewhere | `skipped: earlier version`; nothing changes |
| 10 | Too short | Fewer than 150 words after cleaning | `skipped: too short` |
| 11 | Changed | Path of an `active` or `unreachable` entry, new hash | `changed`: the old entry will be superseded |
| 12 | Near-duplicate | 5-word-shingle Jaccard ≥ 0.90 with another candidate at a different path, or with a cached `active` corpus text at a different path | `skipped: near-duplicate` (see below) |
| 13 | New | Everything else | `new` |

- **Near-duplicates.** Among candidates, the one with the newest **document date** is kept and the
  others are skipped. Document date: Markdown frontmatter `date`, PDF `/CreationDate`, Word
  `dcterms:created`; missing or unparsable → file modification time; equal → the path that sorts
  first (§2.3 case rule) is kept. A cached `active` corpus text is never skipped: a candidate that
  duplicates one is skipped, whatever the dates, and the note names the corpus text. Row 12 never
  compares a file with its own previous version, and entries with `cached: false` have no text and are
  not compared.
- **Unreachable:** after the scan, each `active` entry whose path lies inside the scope and whose hash
  was found nowhere in the scan, and which is not about to be superseded by a `changed` or `reverted` row, is listed
  under `unreachable`. A changed file that became too short (row 10) therefore leaves its old entry
  unreachable. Entries outside the scope are not touched.
- **Cache consistency.** `cached` becomes true only in a change that also writes `corpus/<key>.txt`
  (a text found again after its cache was deleted is re-extracted in the same item). An entry with
  `cached: true` whose `corpus/<key>.txt` is missing is a store inconsistency: the run stops with `status: error` naming the entry. A dry run reports it in `notes`
  and continues.
- **Report.** The inventory report (and the whole output of a dry run) follows
  `inventory-report.schema.json`: one row per text with `path`, `key`, `result`, `words`, `lang`,
  `type`, optional `note`; plus `unreachable`. `lang` and `type` are the resolved values (§12.1);
  `type` is `?` when only the model could tell, since a dry run stops before step 4. `skipped: not
  prose` rows have `key`, `words`, `lang` and `type` null.
- **Comparing with an expected report** (phase 1's exit test, `tests/inventory_compare.py`): rows are
  matched on (`path`, `key`) and must match one to one; `result`, `words`, `lang` and `type` must be
  equal; an expected `key` of null matches any key; `unreachable` must match as a set; `note`,
  `notes`, `not_listed`, `command` and `scope` are not compared.
- `tests/inventory-fixture/` holds a source folder covering the rows, with the expected report in
  `expected-inventory.json`.

## 6. Extraction (adapters)

The cleaned text is a list of **blocks** (paragraphs, headings, list items) joined by one blank line.
Inside a block, line breaks become single spaces.

1. **Markdown** (`markdown-it-py` 4, CommonMark with tables enabled; HTML blocks and inline HTML
   removed):
   1. A YAML frontmatter block (first line `---` to the next `---` line) is removed first; its `date`,
      `tags`, `lang` and `type` are read as metadata.
   2. Removed: fenced and indented code blocks; inline code longer than 40 characters; blockquotes,
      except Obsidian callouts (`> [!type] Title`), whose body is kept and whose title line is
      dropped; tables where more than half of the body cells are numeric (digits with optional
      `.,%€$-` and spaces); images and embeds (`![…](…)`, `![[…]]`); HTML comments; footnote
      definitions; inline `#tags`.
   3. Kept as text: headings without their `#` markers (each its own block); paragraphs; list items
      without their markers (each its own block); inline code of 40 characters or fewer without its
      backticks; link text (`[text](url)` → `text`; `[[note]]` → `note`; `[[note|alias]]` →
      `alias`); emphasis text without its markers; other tables row by row, cells joined by a space.
2. **Word** (`.docx`): read `word/document.xml` directly (not `python-docx`'s `paragraph.text`, which
   drops tracked insertions). Each `w:p` is a block: the text of its `w:t` elements, including those
   inside `w:ins`; `w:delText`, `w:moveFrom` and comments dropped. Empty paragraphs are skipped.
3. **PDF**: `pdfminer.six` `extract_text` with default layout analysis. Each text box is a block;
   lines inside it are joined with a space, and a line ending in `-` before a lower-case letter is
   joined without the hyphen. In a document of three or more pages, lines repeated on at least half
   of the pages (headers, footers) are removed; lines that are only a page number are always removed. A page with no text layer is flagged, never OCR'd
   in v1.
4. **Mail** (phase 5): quoted replies (lines starting `>`, "On … wrote:" blocks) and signatures (from
   a line `-- ` or a detected sign-off block to the end) are removed.
5. **Headings in measurement.** Headings stay in the cached text and the hash, but are not measured:
   see `references/fingerprint.md`.

## 7. Ownership (the ledger)

Ownership is decided **per text and per profile**: one text can be `own` for the house profile
`acme` and `assisted` for the writer `sam`. The manifest stores one ownership record per profile in
the entry's `profiles` map (§8).

1. Precedence for one text and one profile, highest first:
   1. A per-file answer for that profile in the manifest (`decided_by: writer`).
   2. The most specific path rule in `sources.yaml` for that profile (longest path).
   3. A tag rule for that profile.
   4. Undecided: ask.
2. Rules for **different** profiles never conflict; each adds its own profile. Two rules of equal
   specificity for the **same** profile that disagree: ask, and record the answer per file.
3. A **changed** file (same path, new hash), per profile:
   - previously decided by a rule → the rule decides again; nothing is asked.
   - previously decided per file → ask again, offering the previous answer as the default.
4. A text is cached (`cached: true`) when it is `own` for at least one profile and not `forgotten`. A text that is only
   `assisted` or `exclude` gets an entry with `cached: false` and no text on disk.
5. Mail and web sources with no matching rule are always undecided.
6. Ownership answers go to the pending area; they take effect only on approval.

## 8. Manifest lifecycle

Each entry has one `status` for the text, and one ownership record per profile. Allowed changes;
anything else is a bug. Every change except those marked *housekeeping* goes through the pending area.

### Status

| From | To | Trigger |
| --- | --- | --- |
| (new) | `active` | Approved learn of a new text |
| `active` | `superseded` | Approved learn of a changed file at the same path; `superseded_by` set |
| `superseded` | `active` | Approved learn of a reverted file (§5 row 9); the entry that superseded it becomes `superseded` in the same commit |
| `active` | `unreachable` | Inventory: path in scope not found (*housekeeping*, listed in the run report) |
| `unreachable` | `active` | Inventory: same hash found again, at the old or a new path (*housekeeping*) |
| `active`, `unreachable` | `forgotten` | Approved `forget` of the text for **every** profile it feeds; cached text deleted |
| `forgotten` | `active` | Approved `forget <source> ownership=own`: the file is found with the same hash, extracted and cached again. The entry's old profile records are replaced by the new ones, so re-owning for one profile never revives another |
| any | the snapshot's status | Approved `rollback` (below) |

`holdout` can be set on any `active` entry by an approved `test` and is cleared only by `rollback` or
by an approved `forget`.

### Ownership, per profile

| Change | Effect on the entry |
| --- | --- |
| `forget <source>` (by path: the current version and its segments; by key: that text) for one profile of several | That profile's record becomes `exclude`, decided by the writer, so no folder rule gives the text back; status unchanged |
| `forget <source>` for its only (or last) profile | Status `forgotten`; text deleted |
| `forget <source> ownership=assisted` or `exclude` | Record changed; if no profile is `own` any more, text deleted and `cached: false` |
| `forget <source> ownership=own` | Record changed; text extracted and cached if it was not (`cached: true`) |

### Rollback

A snapshot (§11) holds the entries that fed the profile at that moment. For each entry now in the
manifest that feeds the rolled-back profile:

1. In the snapshot: its status, holdout flag and this profile's ownership record are restored. If
   that makes it cached again and the text is gone, the file is re-extracted when its path gives the
   same hash; otherwise it is restored as `unreachable` with `cached: false`, and the report says so.
   **A text another profile also uses keeps its status and holdout flag**: status belongs to the
   text, and a rollback never changes another profile. Only this profile's record is restored (or
   removed), which can leave this profile without that text until its next learn; the diff says so.
2. Not in the snapshot (added later): this profile's record is removed. If no profile remains, the
   entry is removed from the manifest and its text deleted: at the snapshot it did not exist, so a
   later learn sees the text as new again (it is not `forgotten`; the writer never forgot it).
3. Restored to `forgotten`, or owned by no profile any more: its cached text is deleted.
4. `rejected.yaml` is never rolled back: rejections are permanent until the writer lifts them. A
   restored page or list keeps the highest `last_id` of the current version, so ids created after the
   snapshot are never reused.

Entries that do not feed the profile are never touched by its rollback.

## 9. Pending area and approval

1. A store-writing run stages its proposal under `.state/pending/`: every file it would write, at its
   store-relative path, and `.state/pending/plan.json` listing the **items**.
2. An **item** is one thing the writer approves or rejects: a corpus text, an ownership decision, a
   lesson, a ruling, a vocabulary entry, an example, a fingerprint, a status change, a deletion. Each
   item has an id (`i-001`…), a kind, the profile and slot it belongs to, a one-line summary, the
   store-relative `path` of the file it lands in, and a decision (`pending`, `approved`, `rejected`).
   Several items can land in one file (all lessons of a slot page).
3. The diff is grouped per profile and slot. Rejected observed, edit, vocabulary and example items are
   recorded in `rejected.yaml` on commit.
4. **Decisions carry through.** The writer's own decisions are kept apart; effective decisions are
   recomputed from them every time, so approving an item again undoes the knock-on rejections it
   caused, and only the writer's own rejections are recorded in `rejected.yaml`:
   - An item may *require* others: anything of a new profile requires the profile item; each
     profile record a text would get stands on that profile's item and on the new rule that decided
     it, and is dropped when one of them is rejected (the text itself only when all its records go); a text of a new type requires the item adding the
     type; a lesson, example or never-list of a new slot requires that slot's fingerprint. When a
     required item is rejected, so is the item.
   - At commit, a slot removal whose slot still has texts (the change that emptied it was rejected)
     is dropped.
   - An example drawn from a rejected text is rejected; a lesson whose evidence texts are all
     rejected is rejected; other lessons lose the rejected texts from their evidence at commit.
   - An item on a pooled slot that holds exactly the texts of one exact slot *follows* the matching
     item there and takes its decision; the diff shows only the leading item.
   - `forget`, `rollback` and `prune` proposals are **atomic**: rejecting any item rejects all.
5. **Commit** on approval:
   1. Approved fingerprints are re-measured on the approved corpus only, so a rejected text never
      counts; a slot left without texts drops its fingerprint. Then the engine regenerates each
      affected staged file from the **approved** items only. Staged files are never patched by hand.
   2. It writes the **journal**: the `commit` block of `plan.json`, listing every step in order, each
      with state `todo`: first a `snapshot` step per affected profile (§11; not for `prune`, whose purpose is
      removing snapshots), then corpus texts, the
      manifest, profile files, deletions and finally the `changelog` entry.
   3. It applies the journal in order, marking each step `done` after it. Every write is atomic
      (§1.4), so repeating a step is harmless; a snapshot step that finds its folder complete is done.
   4. Clear `.state/pending/` and release the lock.
6. If everything is rejected: record the rejections, clear `.state/pending/`, release the lock, write
   nothing else.
7. **Leftovers.** A pending area found at the start of any store-writing run is shown before anything
   else:
   - with a `commit` block: **resume** continues the journal from its first `todo` step; nothing else
     is offered, because the store is half-written.
   - without one: **resume** reopens the diff; **discard** clears the pending area.
   Nothing else happens until the writer chooses; non-interactive runs stop with `needs_input`.

## 10. Lock

1. **Store-writing modes** are `learn`, `learn-edit`, `interview`, `forget`, `rollback`, `prune` and
   `test` (`test` flags holdout texts and writes `eval/results.md`), and `migrate.py`, which takes the
   lock as mode `migrate` while it upgrades file formats and refuses to run while a pending area waits. Each creates `.state/lock`
   exclusively (create-new, failing if it exists) before its first write, including the pending area.
   Read-only modes (`write`, `rewrite`, `check`, `export`, `status`) and any `dry-run=true` never take
   the lock and read only committed files.
2. The heartbeat is updated at every pipeline step and every script call the run makes. Nothing runs
   between the writer's messages, so a run waiting for the writer does not update it; that case is
   handled by rule 4. The pending area records which lock (its `started` and `mode`) it belongs to;
   every later script call on that pending area checks it still holds that lock, takes it back if it
   was abandoned, and stops if another live run holds it.
3. A lock whose heartbeat is **less than one hour old** blocks: stop and say which mode holds it, since
   when.
4. A lock whose heartbeat is **one hour old or older** is abandoned. The next store-writing run tells
   the writer and takes it over:
   - it writes its own lock to `.state/lock.tmp`, renames it over `.state/lock`, reads it back and
     continues only if it holds its own `started` value (two runs taking over at once: one wins);
   - with no pending area, it starts normally;
   - with a pending area, it offers resume or discard first (§9.7).
   A leftover pending area therefore never locks the store for good.
5. A lock file that is empty or does not validate (a crash while creating it) is treated as a lock
   whose heartbeat is the file's modification time, reported as damaged, and taken over by rule 4.
   This is the one exception to §1.3.
6. The `pending` field in the lock is informational; takeover depends only on the heartbeat.
7. Adding `migrate` to the modes did not bump the lock's `schema_version`: a lock lives only for one
   run, and an older engine that meets a `migrate` lock reads it as damaged (rule 5), which blocks it
   for an hour and never lets it write while the upgrade runs.

## 11. Snapshots, rollback, prune, deletion

1. A snapshot is `profiles/<profile>/snapshots/<UTC timestamp YYYY-MM-DDTHHMMSSZ>/` (a `-2`, `-3` …
   suffix if that name exists; snapshots sort by time, then suffix number) containing a copy of
   every file in the profile folder except `snapshots/`, plus `manifest-entries.json`: the manifest
   entries whose `profiles` include this profile (schema `manifest-entries.schema.json`).
2. `rollback` (latest snapshot when `to=` is omitted):
   1. Takes a new snapshot first.
   2. Restores the profile's files from the snapshot and removes profile files created after it.
   3. Restores manifest entries as set out in §8 (Rollback).
   A profile's first commit takes an empty snapshot (no files, no entries), so the first learn can be
   rolled back too. Entries in the snapshot that the manifest no longer has (an earlier rollback
   removed them) are put back with this profile's record, re-extracted when the file still gives the
   same text. Files created after the snapshot are removed, except the lessons and examples pages,
   `vocabulary.yaml` and `rulings.yaml`, which are emptied so their `last_id` survives.
   A known text that a rule now gives to a profile without a record for it (a new rule, or a record a
   rollback removed) gets that record at the next learn.
   4. Goes through the pending area and approval like any change.
3. `prune` keeps the newest `keep` snapshots (default 10) and deletes the rest.
4. Only `forget`, `rollback` and `prune` delete, always after an approved diff. Where the environment
   needs delete permission, the engine asks for it at that point and explains why.

## 12. Facets, slot keys and resolution

1. Facet values are taken in this order, per facet and per text (a text's facets follow its hash, so
   a copy at another path gets the entry's values): the command; the manifest entry; the most
   specific matching rule's `facets`; frontmatter (`lang`, `type`); detection (`lang` by §4.4, `type`
   by the model from `types`, not in a dry run); `defaults`; else `_` (for `type` in a report: `?`).
   `lang` MUST resolve to a real language; if it cannot, the text is listed as uncertain.
2. The slot key joins one value per declared facet with `.`, in declared order.
3. Pooled slots are built for every key obtained by replacing a suffix of facets (never `lang`) with
   `_`, when at least one text matches.
4. Resolution, given a requested profile and key:

   ```
   for profile in [requested, parent, parent's parent, …]:
       for key in [k, k with last facet as _, k with last two as _, …, lang._…]:
           if profile has slot key: return (profile, key)
   return no_slot
   ```

5. Rulings and vocabulary are merged across the whole chain (child entries override parent entries
   with the same id via `overrides`), whichever slot is returned.

## 13. Confidence

1. Count level: `low` if texts < 3 or words < 3,000; `high` if texts ≥ 8 and words ≥ 15,000;
   otherwise `medium`. The text counts are supported by the phase 0 experiment; the word floors were
   not varied there and stay starting values.
2. Stability level: split the slot's texts (corpus texts and segments in the slot) into two halves
   five times, and measure the applicable global metrics (§17.1) on each half joined with blank lines.
   - Seed: `int(sha256("<profile>/" + "|".join(sorted text keys)).hexdigest()[:8], 16)`, stored as
     the fingerprint's `seed`. Basing it on the texts, not the slot name, gives a pooled slot that
     holds exactly the texts of one exact slot the same confidence. RNG: Python `random.Random(seed)`; texts sorted by key first; each split is
     `order = rng.sample(texts, len(texts))`, halves `order[:n // 2]` and `order[n // 2:]`; the five
     splits draw from the same RNG in sequence.
   - With fewer than 2 texts no split is made and the stability level equals the count level.
   - The relative difference of a metric is `|a − b| / max(floor, (a + b) / 2)`. A metric is
   **unstable** when that difference exceeds its own `stability_tolerance` (from
   `assets/global-metrics.json`) in 2 or more of the 5 splits. If the number of unstable metrics is at
   least the **downgrade count**, the stability level is one step below the count level; otherwise
   equal to it.
   - Downgrade count: as the fail count in §17.2, from `downgrade_fraction`: 4 for 11 to 14 metrics.
   - Measured in phase 0: a genuine single-author corpus is downgraded 60% of the time at 3 texts,
     32% at 5, 10% at 8 and 2% at 12; a corpus mixing two authors 60% at 8 and 36% at 12. So most
     slots under 8 texts drop one level: small slots are honestly less settled.
3. Confidence = the lower of the two. It is written to the fingerprint and copied to the slot page.

## 14. Lessons, ids and rejections

1. An observed lesson needs at least two supporting corpus texts; an edit lesson at least two stored
   edit pairs. One is "Seen once".
2. Every lesson and record has an id, allocated per file as the next unused number with its
   prefix, never reused even after deletion:

   | Prefix | What | Where |
   | --- | --- | --- |
   | `l-` | Observed lesson | Slot page, `- [l-003] …` at the start of the item |
   | `d-` | Edit lesson | `<slot>.edits.md`, `- [d-002] …` |
   | `r-` | Ruling | `rulings.yaml` |
   | `v-` | Vocabulary entry | `vocabulary.yaml` |
   | `e-` | Example passage | `<slot>.examples.md` |
   | `p-` | Edit pair | `edits/p-NNN/` |
   | `c-` | Change within an edit pair | `pair.yaml` |
   | `x-` | Rejection | `rejected.yaml`, with the rejected item's id in `rejects` |
   | `i-` | Pending item | `.state/pending/plan.json` only |

   The next number is above every number the file has used, including ids of items rejected in this
   proposal and ids named by `rejects` in `rejected.yaml`. A slot left without texts keeps its lessons
   page and examples page, emptied, so their `last_id` survives.

   On relearn, a proposed lesson whose normalised form (below) equals an existing lesson's in the
   same slot keeps that lesson's id; otherwise it gets a new one. So a ruling promoted from `l-003`,
   or a rejection of it, still points at the same lesson after a relearn.
3. Normalised form for rejections: lower-case, remove punctuation, remove the stop words in
   `references/lang/<lang>/stopwords.txt`, collapse spaces. A proposal whose normalised form equals a
   rejection's for the same slot is dropped; the model flags likely rewordings for the writer.

## 15. Redaction

1. Script pass: e-mail addresses, phone numbers, URLs with personal paths, postal codes, IBANs.
2. Model pass: names of people and organisations other than the writer's own, replaced with
   `[person]`, `[client]`, `[employer]`, `[organisation]`.
3. Applied to example passages, lesson evidence quotes, edit pairs and, for mail, the cached text.
4. Every redacted item records `{redacted: true, version, reviewed}`; the diff shows each replacement.

## 16. Edge cases

| Case | Behaviour |
| --- | --- |
| How-to that is mostly code | Code stripped; skipped under 150 words of prose |
| Text switching language | A run of consecutive 40+-word paragraphs identified as the same other language (confidence ≥ 0.9) becomes one segment (§4.4) |
| Long quote from someone else | Stripped before learning; untouched in rewrites |
| Slot from one or two texts | Usable at `low`; lessons still need two supporting texts |
| Mixed ownership in one file | Asked per file; not learned until answered |
| Source moved or renamed | Same hash: manifest path updated; no question (§5 row 7) |
| Source edited | New hash supersedes the old entry, shown in the diff |
| Source deleted | Marked unreachable; still learned until `forget` |
| Store inside a learn target | Skipped by the inventory |
| Store unreachable | Write and rewrite work from slot files the writer attaches; learn waits |
| Two store-writing runs | The second stops on the lock |
| Unquoted date in YAML | Read as a string (§1.2) |
| `lang: no` unquoted | The string `no`, not false (§1.2) |
| Leftover pending area | Resume or discard offered first; an abandoned lock is taken over (§9.7, §10.4) |
| One text, two profiles | Ownership per profile (§7); forgetting it for one keeps it for the other |
| Store file fails validation | Run stops with `status: error` naming the file |

## 17. Check decision

1. `check` uses the **applicable global metrics**: the 14 in `global-metrics.json`, minus those whose
   word list is missing for the text's language (`references/fingerprint.md`), so 11 to 14. Primary
   metrics from the contrast pass steer drafting and order the hints; they do not shorten the list.
   For each metric: if the writer's value is below the metric's `floor`, flag when the draft exceeds
   it by more than 2 × `floor` (`ratio` is then null in the report); otherwise flag when
   `draft / writer` is above `overshoot` or, for non-sparse metrics, below `shortfall`.
2. The **fail count** is `min(n, max(min_count, ceil(p × n / 100)))` in integer arithmetic, where n is
   the number of applicable metrics and p = `round(fail_fraction × 100)` (28): 4 for 11 to 14
   metrics. `status` is `fail` when the number of flagged metrics is at least the fail count;
   otherwise `pass`, or `low_confidence` when the slot's confidence is `low`. The report records
   `flagged` and the resolved count as `fail_threshold`.
3. The stability downgrade count (§13.2) is computed the same way from `downgrade_fraction`.
4. Every flag is still reported in the report, as a hint for the rewrite.

## 18. Values set in phase 0

All from `evals/spike/RESULTS.md`, shipped in `idiolect/assets/global-metrics.json`.

| Value | Result |
| --- | --- |
| Global metric list | 14 metrics, listed in RESULTS.md |
| Overshoot, shortfall, floor per metric | In `global-metrics.json`; five metrics are sparse (overshoot only) |
| Stability tolerance | Per metric, 0.14 to 1.50 (capped: the relative difference cannot exceed 2.0) |
| Downgrade count | `downgrade_fraction` 0.28 → 4 of 14 unstable metrics (10% of genuine 8-text corpora downgraded, 60% of two-author mixes) |
| Fail count for `check` | `fail_fraction` 0.28 → 4 of 14 flagged metrics (17% of genuine passages fail, 80% of AI rewrites; real authors 18% / 70%, synthetic 0% / 100%) |
| Count thresholds | Text counts supported (`low` < 3 texts, `high` ≥ 8); word floors 3,000 and 15,000 untested starting values |
| Near-duplicate threshold | 0.90 confirmed (distinct essays peak at 0.004) |
