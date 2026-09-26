# Mode: learn

Learns from a file, folder or tag (none = every registered source). One proposal, one diff, one
approval. Scripts do everything that can be counted; you do the steps marked **model**. Run every
script from the skill folder; each prints JSON, and `learn.py --store S next` always says what is
left.

## 0. Before anything

- `scripts/check_env.py`; find the store (SKILL.md). No store: ask where to create one (never inside
  a folder you will learn from), then create it with `idiolect.yaml` from `assets/templates/`.
- Offer a dry run first for a large folder (`inventory.py --dry-run`).

## 1. Start

```
python3 scripts/learn.py --store S start [--target REL]... [--tag T]... [--profile P] [--lang L] [--type T]
```

Takes the lock and inventories. If it says a pending area is waiting, show `stage.py diff` and ask
the writer: **resume** (continue deciding, or `stage.py resume` if a commit had started) or
**discard** (`stage.py discard`). Relay the inventory summary in two or three lines.

## 2. Ownership (writer)

`learn.py questions` lists texts no rule decides, grouped by folder, and profiles that do not exist
yet. Ask **once per folder**, not per file: "Are the texts in `Published/` all yours? Any exceptions?"
Offer `own` (learned), `assisted` (recorded, not learned; e.g. co-written or heavily edited by
someone else) and `exclude`. For a new profile ask whose voice it is and record consent: `self` for
the user, a consent record for anyone else. Refuse a profile meant to impersonate someone.

Write the answers to a YAML file and apply them:

```yaml
folders:
  - {path: Published, profile: sam, ownership: own, facets: {type: essay}, exclude: ["guest-*"]}
files:
  - {path: Published/2024-guest-post.md, profile: sam, ownership: exclude}
profiles:
  - {name: sam, subject: "Sam, the user", consent: self}
```

`learn.py --store S answer --file answers.yaml`. Repeat until `questions` is empty. With
`interactive=false`, stop with `needs_input` and the question instead.

## 3. Types (model)

`learn.py types` lists texts whose type no rule, frontmatter or command sets, with a 300-word
excerpt and the allowed `types`. Pick one per text; propose a new type only when none fits, and say
so in the diff. Write `{path: type}` YAML and run `learn.py set-types --file types.yaml`.

## 4. Stage texts and measure (script)

```
python3 scripts/learn.py --store S stage-texts
python3 scripts/learn.py --store S measure
```

`measure` lists the affected slots with counts and confidence. A pooled slot that holds exactly the
same texts as one exact slot **mirrors** it: its contrast and lessons are copied automatically.

## 5. Contrast (model, in a fresh context)

For each slot `next` names: `learn.py contrast-sample --profile P --slot K`. If it answers
`reuse: true`, skip the slot. Otherwise give the paragraphs and the brief to a **fresh agent that has
no skill loaded and has never seen the corpus**; it writes rewrite `N` to `rewrites_dir/N.txt`. If no
fresh agent is available, do it yourself and pass `--fresh false` (the diff says it is less
reliable). Then:

```
python3 scripts/learn.py --store S contrast-apply --profile P --slot K --rewrites <rewrites_dir>
```

## 6. Lessons (model)

`learn.py lessons-sample --profile P --slot K` writes a stratified sample (at most 20,000 words; each
text starts with `### text <key>`) and lists existing lessons and rejected proposals. Read the sample
and write observed lessons:

- **About style, never content.** How the writer opens, builds, ends, sentences, tone, recurring
  devices; never topics, opinions, facts, names or anecdotes.
- **Concrete and checkable**: "Opens with a single short sentence that states the problem", not
  "Engaging openings".
- **Evidence**: list the text keys where the pattern clearly occurs (two or more for a lesson; one
  goes to Seen once automatically) and one short verbatim `quote` (under 20 words) from one of them.
- **Sections**: Stance, Openings, Structure, Endings, Sentences, Tone, Recurring devices.
- Keep the wording of an existing lesson when it still holds, so it keeps its id. Do not re-propose
  a rejected one in other words; if you are unsure whether something is a rewording, say so to the
  writer instead of proposing it.
- Aim for 6 to 15 lessons per slot. Fewer, sharper lessons beat many vague ones.

```yaml
- {section: Sentences, text: "Follows a long sentence with a very short one.", evidence: [<key>, <key>], quote: "It broke. Nobody noticed."}
```

`learn.py lessons-apply --profile P --slot K --file lessons.yaml [--names names.yaml]`. It drops
rejected proposals, checks quotes against their texts, redacts quotes, keeps ids and proposes
removal of lessons you did not re-propose.

## 7. Vocabulary and examples (model)

- Vocabulary: terms, spellings and coinages the writer uses on purpose (`kind`: term, spelling,
  coinage, keep). Mark anything personal or client-related `private: true`. Write a YAML list and run
  `learn.py vocab-apply --profile P --file vocab.yaml`.
- Examples, per exact slot: `learn.py examples-sample --profile P --slot K` gives candidates. Pick
  3 to 6 that show the voice best, each with a `habit` it illustrates. List every name of a person or
  organisation other than the writer under `names` with a placeholder (`[person]`, `[client]`,
  `[employer]`, `[organisation]`). Run `learn.py examples-apply --profile P --slot K --file examples.yaml`.

```yaml
names: [{name: "Jane Doe", placeholder: "[person]"}]
examples: [{key: <key>, text: "<exact passage>", habit: "long-then-short rhythm"}]
```

## 8. Diff and approval (writer)

`stage.py --store S diff` shows every item grouped per profile and slot. Show it (shorten long
lists), then ask what to reject. Rulings: when the writer says a lesson is "always" or "never", add
`learn.py rule --profile P --text "..." --from l-002`. Apply decisions with
`stage.py decide --approve all` or `--reject i-004,i-009` (then `--approve all` for the rest), and
`stage.py commit`. Say what was learned in two lines: slots, confidence, lessons added, rejected.

Never approve on the writer's behalf. If the session ends before approval, the next run offers
resume or discard.
