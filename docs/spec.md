# Idiolect rules specification (v1)

This document turns the design's rules into precise, testable behaviour. `docs/design.md` says
*what* and *why*; this says *exactly how*. Where they disagree, fix one of them in the same commit.

**MUST**, **SHOULD** and **MAY** have their usual meaning. Values measured in the phase 0 metric
experiment are listed in §18 and explained in `evals/spike/RESULTS.md`.

## 1. Files, encoding and loading

1. All store files are UTF-8 without BOM, LF line endings.
2. YAML MUST be loaded with a safe loader that keeps dates and times as strings (no timestamp
   resolution). A writer typing `created: 2026-10-02` without quotes gets a string, not a date object.
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
   2. Replace every run of whitespace (including line breaks) with a single space.
   3. Strip leading and trailing space. Case is kept.
   4. Encode as UTF-8; SHA-256; lower-case hex.
3. Metadata-only changes (file dates, PDF producer, Word properties) therefore never change the hash.
4. A mixed-language file keeps the whole-file hash as its key for the main language; each split-off
   segment is `<hash>#n` (n = 2, 3, …, in order of appearance), stored as `<hash>-n.txt`.

## 5. Inventory classification

Applied in this order; the first match decides.

| Check | Rule | Result |
| --- | --- | --- |
| Excluded | Matches a global `exclude` glob or the rule's own `exclude` | Not listed at all |
| No adapter | Extension not handled by an available adapter | Skipped: not prose |
| Holdout | Hash is flagged `holdout: true` in the manifest | Skipped: holdout |
| Too short | Fewer than 150 words of prose after cleaning | Skipped: too short |
| Near-duplicate | 5-word-shingle Jaccard similarity ≥ 0.90 with another candidate or an active text | Keep the newest (document date, then modification time); skip the others |
| Unchanged | Hash already in the manifest with `status: active` | Unchanged |
| Changed | Same path as an active entry, new hash | Changed (the old entry will be superseded) |
| New | Everything else | Usable |

Manifest entries whose path is no longer found are reported as **unreachable**.

## 6. Extraction (adapters)

1. Removed before caching: frontmatter, code blocks and inline code longer than 40 characters, tables
   whose cells are mostly numbers, quoted replies (lines starting `>` in mail, "On … wrote:" blocks),
   signatures (from a line `-- ` or a detected sign-off block to the end), and blockquotes.
2. Kept: headings (as plain lines), paragraphs, list items.
3. `docx`: tracked insertions kept, deletions dropped, comments dropped, read from `word/document.xml`.
4. `pdf`: text layer only; a page with no text layer is flagged, never OCR'd in v1.

## 7. Ownership (the ledger)

1. Precedence, highest first:
   1. A per-file answer in the manifest (`decided_by: writer`).
   2. The most specific matching path rule in `sources.yaml` (longest path).
   3. A matching tag rule.
   4. Undecided: ask.
2. Two rules of equal specificity that disagree: ask, and record the answer per file.
3. A **changed** file (same path, new hash):
   - previously decided by a rule → the rule decides again; nothing is asked.
   - previously decided per file → ask again, offering the previous answer as the default.
4. `assisted` and `exclude` texts get a manifest entry with `cached: false` and no text on disk.
   Promoting one to `own` (`forget … ownership=own`) extracts and caches it then.
5. Mail and web sources with no matching rule are always undecided.
6. Ownership answers go to the pending area; they take effect only on approval.

## 8. Manifest lifecycle

Allowed transitions; anything else is a bug.

| From | To | Trigger |
| --- | --- | --- |
| (new) | `active` | Approved learn of an `own`, `assisted` or `exclude` text |
| `active` | `superseded` | Approved learn of a changed file at the same path; `superseded_by` set |
| `active` | `unreachable` | Path not found during an inventory |
| `unreachable` | `active` | Path found again with the same hash |
| `active`, `unreachable` | `forgotten` | Approved `forget`; cached text deleted |

`superseded` and `forgotten` are final. Their entries stay in the manifest for history; they never
feed learning. `holdout` can be set on any `active` entry by an approved `test` and is never cleared
automatically.

## 9. Pending area and approval

1. A store-writing run stages every proposed file under `.state/pending/` at its store-relative path,
   and lists each change in `.state/pending/plan.json`.
2. The diff is grouped per profile and slot. The writer may approve or reject each item; rejected
   observed, edit or vocabulary proposals are recorded in `rejected.yaml` on commit.
3. **Commit order** on approval:
   1. Take a snapshot (§11) of every affected profile.
   2. Apply approved items with atomic writes, corpus text first, then manifest, then profile files.
   3. Append the changelog entry.
   4. Clear `.state/pending/` and release the lock.
4. If everything is rejected: clear `.state/pending/`, release the lock, write nothing else.
5. A pending area found at the start of any store-writing run is shown first, with resume or discard.
   Nothing else happens until the writer chooses.

## 10. Lock

1. Every store-writing mode creates `.state/lock` exclusively before its first write (including the
   pending area). If it exists and is not stale, stop and say which mode holds it since when.
2. The heartbeat is updated at every pipeline step and at least every five minutes.
3. A lock is **stale** when its heartbeat is older than one hour **and** no pending area exists.
   A stale lock may be taken over after telling the writer.
4. `dry-run=true` and read-only modes never take the lock.

## 11. Snapshots, rollback, prune, deletion

1. A snapshot is `profiles/<profile>/snapshots/<UTC timestamp YYYY-MM-DDTHHMM>/` containing a copy of
   every file in the profile folder except `snapshots/`, plus `manifest-entries.json`: the manifest
   entries whose `profiles` include this profile.
2. `rollback` (latest snapshot when `to=` is omitted):
   1. Takes a new snapshot first.
   2. Restores the profile's files from the snapshot and removes profile files created after it.
   3. Restores manifest entries listed in the snapshot. For entries created after it: if this profile
      is the only one in `profiles`, the entry becomes `forgotten` and its text is deleted; otherwise
      this profile is removed from `profiles`.
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
2. Ids are allocated per file as the next unused number with the file's prefix (`r-`, `v-`, `x-`,
   `e-`, `p-`) and are never reused, even after deletion.
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
| Source moved or renamed | Same hash: manifest path updated in the diff; no question |
| Source edited | New hash supersedes the old entry, shown in the diff |
| Source deleted | Marked unreachable; still learned until `forget` |
| Store inside a learn target | Skipped by the inventory |
| Store unreachable | Write and rewrite work from slot files the writer attaches; learn waits |
| Two store-writing runs | The second stops on the lock |
| Unquoted date in YAML | Read as a string (§1.2) |
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
