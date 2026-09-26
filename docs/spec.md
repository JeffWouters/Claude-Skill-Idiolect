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
   load YAML this way (`tests/yaml12.py`), and `tests/invalid-yaml/` holds the cases.
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
   `sources_root`.

## 3. Store discovery

1. `store=<path>` wins. If the path has no valid `idiolect.yaml`, stop with `status: no_store`.
2. Otherwise search the folders the session can reach, breadth-first, at most three levels deep,
   skipping hidden folders, `node_modules`, `.git` and `_to_delete`. A folder qualifies if it holds an
   `idiolect.yaml` that validates.
3. One hit: use it and name it. Several: list them and ask (`needs_input` when non-interactive). None:
   on `learn`, offer to create one and ask where (never inside a folder being learned from); on any
   other mode, stop with `no_store`.
4. Nothing about the chosen store is remembered between sessions.

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
4. A mixed-language file keeps the whole-file hash as its key for the main language; each split-off
   segment is `<hash>#n` (n = 2, 3, …, in order of appearance), stored as `<hash>-n.txt`.

## 5. Inventory classification

The inventory runs over one **scope**: the targets of this run (a file, a folder, a tag), or every
registered source when `learn` has no target. Each found file is extracted (§6) and hashed (§4); a
mixed-language file yields several texts, each classified on its own. The checks run in this order;
the first match decides.

| # | Check | Rule | Result |
| --- | --- | --- | --- |
| 1 | Excluded | Inside the store root (§2.5), or matches a global `exclude` glob or the rule's own `exclude` | Not listed |
| 2 | No adapter | Extension not handled by an available adapter | Skipped: not prose |
| 3 | Unsupported language | Detected language written without spaces between words | Skipped: language not supported |
| 4 | Known hash, `forgotten` | | Skipped: forgotten (relearning needs `forget <source> ownership=own`) |
| 5 | Known hash, `holdout: true` | | Skipped: holdout |
| 6 | Known hash, `active` or `unreachable`, same path | | Unchanged (an `unreachable` entry returns to `active`) |
| 7 | Known hash, `active` or `unreachable`, other path | Old path no longer found | Moved: path updated, nothing relearned |
| 8 | Known hash, `active`, other path | Old path still found | Copy: one entry keeps the old path; the copy is reported, not learned twice |
| 9 | Known hash, `superseded`, same path | The file went back to an earlier version | Reverted: that entry returns to `active`; the current one at the path is superseded by it |
| 10 | Too short | Fewer than 150 words of prose after cleaning | Skipped: too short |
| 11 | Changed | Path of an `active` entry, new hash | Changed: the old entry will be superseded |
| 12 | Near-duplicate | 5-word-shingle Jaccard ≥ 0.90 with another candidate at a different path, or with an `active` text at a different path | Keep the newest (document date, then modification time); skip the others as near-duplicates |
| 13 | New | Everything else | Usable |

- Check 12 never compares a file with its own previous version, so an edited file is always
  **changed**, never a near-duplicate of itself.
- **Unreachable:** after the scan, each `active` entry whose path lies inside the scope and was not
  found, and whose hash was not found elsewhere, is reported as unreachable. Entries outside the
  scope are not touched: learning one file never marks the rest of the corpus unreachable.
- **Dry run** reports every row with its path, result, words, and detected `lang`. It reports `type`
  only when a rule, frontmatter or the command sets it, otherwise `?`, because type detection needs
  the model (pipeline step 4) and a dry run stops before it.
- `tests/inventory-fixture/` holds a source folder covering every row, with the expected report in
  `expected-inventory.json`. Phase 1 is done when the inventory reproduces it.

## 6. Extraction (adapters)

1. Removed before caching: frontmatter, code blocks and inline code longer than 40 characters, tables
   whose cells are mostly numbers, quoted replies (lines starting `>` in mail, "On … wrote:" blocks),
   signatures (from a line `-- ` or a detected sign-off block to the end), and blockquotes.
2. Kept: headings (as plain lines), paragraphs, list items.
3. `docx`: tracked insertions kept, deletions dropped, comments dropped, read from `word/document.xml`.
4. `pdf`: text layer only; a page with no text layer is flagged, never OCR'd in v1.

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
4. A text is cached (`cached: true`) when it is `own` for at least one profile. A text that is only
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
| `forgotten` | `active` | Approved `forget <source> ownership=own`: the file is found with the same hash, extracted and cached again |
| any | the snapshot's status | Approved `rollback` (below) |

`holdout` can be set on any `active` entry by an approved `test` and is cleared only by `rollback` or
by an approved `forget`.

### Ownership, per profile

| Change | Effect on the entry |
| --- | --- |
| `forget <source>` for one profile of several | That profile's record is removed from `profiles`; status unchanged |
| `forget <source>` for its only (or last) profile | Status `forgotten`; text deleted |
| `forget <source> ownership=assisted` or `exclude` | Record changed; if no profile is `own` any more, text deleted and `cached: false` |
| `forget <source> ownership=own` | Record changed; text extracted and cached if it was not (`cached: true`) |

### Rollback

A snapshot (§11) holds the entries that fed the profile at that moment. For each entry now in the
manifest that feeds the rolled-back profile:

1. In the snapshot: its status, holdout flag and this profile's ownership record are restored. If
   that makes it cached again and the text is gone, the file is re-extracted when its path gives the
   same hash; otherwise it is restored as `unreachable` with `cached: false`, and the report says so.
2. Not in the snapshot (added later): this profile's record is removed. If no profile remains, the
   entry becomes `forgotten` and its text is deleted.

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
4. **Commit** on approval:
   1. The engine regenerates each affected staged file from the **approved** items only. Staged files
      are never patched by hand.
   2. It writes the **journal**: the `commit` block of `plan.json`, listing every write and deletion
      in order, each with state `todo`.
   3. Take a snapshot (§11) of every affected profile.
   4. Apply the journal in order, marking each step `done` after it: corpus texts, then the manifest,
      then profile files, then deletions, then the changelog entry. Every write is atomic (§1.4), so
      repeating a step is harmless.
   5. Clear `.state/pending/` and release the lock.
5. If everything is rejected: record the rejections, clear `.state/pending/`, release the lock, write
   nothing else.
6. **Leftovers.** A pending area found at the start of any store-writing run is shown before anything
   else:
   - with a `commit` block: **resume** continues the journal from its first `todo` step; nothing else
     is offered, because the store is half-written.
   - without one: **resume** reopens the diff; **discard** clears the pending area.
   Nothing else happens until the writer chooses; non-interactive runs stop with `needs_input`.

## 10. Lock

1. **Store-writing modes** are `learn`, `learn-edit`, `interview`, `forget`, `rollback`, `prune` and
   `test` (`test` flags holdout texts and writes `eval/results.md`). Each creates `.state/lock`
   exclusively before its first write, including the pending area. Read-only modes (`write`,
   `rewrite`, `check`, `export`, `status`) and any `dry-run=true` never take the lock and read only
   committed files.
2. The heartbeat is updated at every pipeline step, while waiting for the writer, and at least every
   five minutes.
3. A lock whose heartbeat is **one hour old or newer** blocks: stop and say which mode holds it, since
   when.
4. A lock whose heartbeat is **older than one hour** is abandoned. The next store-writing run tells
   the writer and takes it over:
   - with no pending area, it starts normally;
   - with a pending area, it offers resume or discard first (§9.6).
   A leftover pending area therefore never locks the store for good.

## 11. Snapshots, rollback, prune, deletion

1. A snapshot is `profiles/<profile>/snapshots/<UTC timestamp YYYY-MM-DDTHHMM>/` containing a copy of
   every file in the profile folder except `snapshots/`, plus `manifest-entries.json`: the manifest
   entries whose `profiles` include this profile (schema `manifest-entries.schema.json`).
2. `rollback` (latest snapshot when `to=` is omitted):
   1. Takes a new snapshot first.
   2. Restores the profile's files from the snapshot and removes profile files created after it.
   3. Restores manifest entries as set out in §8 (Rollback).
   4. Goes through the pending area and approval like any change.
3. `prune` keeps the newest `keep` snapshots (default 10) and deletes the rest.
4. Only `forget`, `rollback` and `prune` delete, always after an approved diff. Where the environment
   needs delete permission, the engine asks for it at that point and explains why.

## 12. Facets, slot keys and resolution

1. Facet values are taken in this order, per facet: command, ledger (manifest entry, then the
   matching rule's `facets`), detection (`lang` by script, `type` by model from `types`), `defaults`,
   else `_`. `lang` MUST resolve to a real language; if it cannot, the text is listed as uncertain.
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
   otherwise `medium` (confirmed by the phase 0 experiment).
2. Stability level: split the slot's corpus into two random halves five times with the slot's seed;
   measure the slot's metric list (primary metrics, or the global list before any contrast pass) on
   each half. The relative difference of a metric is `|a − b| / max(floor, (a + b) / 2)`. A metric is
   **unstable** when that difference exceeds its own `stability_tolerance` (from
   `assets/global-metrics.json`) in 2 or more of the 5 splits. If the number of unstable metrics is at
   least the **downgrade count**, the stability level is one step below the count level; otherwise
   equal to it.
   - Downgrade count = `max(min_count, ceil(downgrade_fraction × metrics in the list))`: 4 for the
     14 global metrics.
   - Measured in phase 0: a genuine single-author corpus is downgraded 10% of the time at 8 texts and
     2% at 12; a corpus mixing two authors 60% and 36%.
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
| Text switching language | Paragraphs of 40+ words identified as another language with probability ≥ 0.9 become a segment |
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
| Leftover pending area | Resume or discard offered first; an abandoned lock is taken over (§9.6, §10.4) |
| One text, two profiles | Ownership per profile (§7); forgetting it for one keeps it for the other |
| Store file fails validation | Run stops with `status: error` naming the file |

## 17. Check decision

1. For each metric in the slot's list: if the writer's value is below the metric's `floor`, flag when
   the draft exceeds it by more than 2 × `floor`; otherwise flag when `draft / writer` is above
   `overshoot` or, for non-sparse metrics, below `shortfall`.
2. The **fail count** is `max(min_count, ceil(fail_fraction × metrics in the list))`: 4 for the 14
   global metrics. `status` is `fail` when the number of flagged metrics is at least the fail count;
   otherwise `pass`, or `low_confidence` when the slot's confidence is `low`. The report records the
   resolved count as `fail_threshold`.
3. Every flag is still reported in the report, as a hint for the rewrite.

## 18. Values set in phase 0

All from `evals/spike/RESULTS.md`, shipped in `idiolect/assets/global-metrics.json`.

| Value | Result |
| --- | --- |
| Global metric list | 14 metrics, listed in RESULTS.md |
| Overshoot, shortfall, floor per metric | In `global-metrics.json`; five metrics are sparse (overshoot only) |
| Stability tolerance | Per metric, 0.14 to 1.50 (capped: the relative difference cannot exceed 2.0) |
| Downgrade count | `downgrade_fraction` 0.28 → 4 of 14 unstable metrics (10% of genuine 8-text corpora downgraded, 60% of two-author mixes) |
| Fail count for `check` | `fail_fraction` 0.28 → 4 of 14 flagged metrics (17% of genuine passages fail, 80% of AI rewrites; real authors 18% / 70%, synthetic 0% / 100%) |
| Count thresholds | Confirmed: `low` < 3 texts, `high` ≥ 8 texts and 15,000 words |
| Near-duplicate threshold | 0.90 confirmed (distinct essays peak at 0.004) |
