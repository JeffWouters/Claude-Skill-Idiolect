# Mode: learn-edit

Learns from how the writer edited a draft: the draft (usually one Idiolect wrote) and the final
version the writer published or approved (spec §20). Store-writing: nothing changes until the writer
approves the diff. Neither version enters the corpus; only the changes are kept, redacted.

## From the edit queue

When the writer asks to process their edit queue, or a scan left items waiting (`published.md`), take
the draft and final version from each waiting item of `published.py queue` and run the steps below;
close each item with `published.py done --id q-NNN` after the commit, or with `--skipped` when the
writer skips it.

## 1. Start

Ask for the draft and the final version if the request does not give both (files, or text you save to
files). Before starting, read both and list the names of people and organisations other than the
writer's own; they go in a names file (`- {name: Jane Doe, placeholder: "[person]"}`, `[client]`,
`[employer]`, `[organisation]`).

```
python3 scripts/learn_edit.py --store S start --draft draft.md --final final.md [--profile P] [--type T] [--facet channel=x] [--names names.yaml]
```

- `needs_input` for the type: ask which type the final version is (the store's `types`).
- It prints the slot, the new pair's id and the changes, each already redacted.

## 2. Name the kinds

For every change, name the kind of edit as a short slug: `cut-hedge`, `split-sentence`,
`plainer-word`, `active-voice`, `cut-intro`, `numerals`, `other` for a change with no general pattern
(a fact corrected, a sentence rewritten for content). Reuse a kind the slot's edit lessons already
name when it is the same kind of edit (`<slot>.edits.md`, the kind is the first word of each
lesson's evidence). Describe every kind that has no lesson yet in one sentence about style, never
content ("Cuts hedges before a claim.").

```yaml
changes: {c-001: cut-hedge, c-002: split-sentence, c-003: other}
describe: {cut-hedge: "Cuts hedges before a claim.", split-sentence: "Splits a long sentence joined by 'and' into two."}
```

```
python3 scripts/learn_edit.py --store S kinds --file kinds.yaml
```

A kind found in two or more stored pairs becomes an edit lesson; in one pair it is "Seen once".

## 3. Diff, approve, commit

`stage.py diff`, then the writer's decisions and `stage.py commit`, as in `learn`. Rejecting the pair
rejects the lessons that stand on it. Say that edit lessons outrank observed lessons in every draft,
that a relearn never removes them, and that a lesson the writer calls "always" or "never" can be made a
ruling.

## interactive=false

Never ask: return `needs_input` with the question (the missing type or version). A proposal waits for
the writer's approval, so return `needs_input` after `kinds` with the diff summary.
