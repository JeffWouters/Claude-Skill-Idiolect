# Markdown page contracts (schema_version 1)

Store files meant for people to read are Markdown with a fixed structure. Each starts with YAML
frontmatter carrying `schema_version` and the fields below. Headings are exact and in this order;
a heading with nothing under it keeps the line `_None yet._`. Scripts parse by heading, so renaming
one is a format change and needs a migration.

## Slot page — `profiles/<profile>/<slot>.md`

```markdown
---
schema_version: 1
profile: sam
slot: en.essay
pooled: false
built: 2026-10-02T21:40:00Z
personal_data: none
---
## Confidence
## Stance
## Openings
## Structure
## Endings
## Sentences
## Tone
## Recurring devices
## Seen once
```

- `## Confidence` is one line copied from the fingerprint, e.g. `medium (count: high, stability: medium)`.
  The fingerprint JSON is the source; the page is never edited to change it.
- Every lesson under the other headings is one list item that starts with its id and ends in its
  evidence (ids: spec §14.2):
  `- [l-003] Short sentences land a point after a long one. _(12 texts; "It broke. Nobody noticed.")_`
  The quote is redacted. `## Seen once` items carry `_(1 text)_`.

## Edit lessons — `profiles/<profile>/<slot>.edits.md`

```markdown
---
schema_version: 1
profile: sam
slot: en.essay
personal_data: none
---
## Edit lessons
## Seen once
```

Each item starts with its id and ends in its evidence:
`- [d-002] Cuts hedges before a claim. _(3 pairs: p-001, p-004, p-007)_`.

## Examples — `profiles/<profile>/<slot>.examples.md`

```markdown
---
schema_version: 1
profile: sam
slot: en.essay
examples:
  - id: e-001
    source: 9f2c…e41a
    habit: long-then-short rhythm
    redaction: {redacted: true, version: "1.0", reviewed: true}
---
## e-001
<the redacted passage>
```

One `## <id>` heading per example, matching the frontmatter list. `export` refuses any example whose
frontmatter entry lacks `redaction.redacted: true`.

## Never-list — `profiles/<profile>/<slot>.never.md`

```markdown
---
schema_version: 1
profile: sam
slot: en.essay
personal_data: none
---
## Never does
```

Items are markers from the contrast pass, each with the rate seen in the AI rewrites against the
writer's rate: `- "It is worth noting that" _(AI 2.1 per 1k words, writer 0)_`.

## Changelog — `profiles/<profile>/changelog.md`

```markdown
---
schema_version: 1
profile: sam
---
## 2026-10-02T21:40:00Z · learn · run 20261002T211000Z
- Slots: en.essay, en._
- Summary: 17 texts added; 9 observed lessons; 1 rejected (x-001); 1 promoted (r-001).
- Snapshot: snapshots/2026-10-02T2140/
```

Newest entry last. Modes that write here: learn, learn-edit, interview, forget, rollback, prune.

## Test results — `eval/results.md`

```markdown
---
schema_version: 1
---
| Date | Profile | Slot | Snapshot | Holdout | Blind picks | Drift (primary metrics) |
| --- | --- | --- | --- | --- | --- | --- |
```

One row per `test` run. `Blind picks` is `—` when no judge was used.
