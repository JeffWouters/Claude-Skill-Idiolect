# Idiolect

A Claude skill that learns a writer's voice from their own texts and writes, rewrites and checks
text in that voice.

Idiolect is an empty engine. The skill holds the method only. What it learns lives in a separate
folder the writer chooses (the *store*), and nothing is learned without the writer approving a diff.

> **Status: phase 0 (groundwork).** The design is complete; schemas, rules, test fixtures and the
> evaluation protocol are being written. There is no runnable skill yet.

## Why "Idiolect"

An idiolect is the linguistic term for one person's own way of using a language. That is exactly
what this skill learns, and nothing else.

## What it will do

- **Learn** from Markdown, PDF and Word files, a folder or a tag, and later from mail, web pages and
  transcripts. Only texts the writer marks as their own are used.
- **Keep lessons** in the writer's store, split into profiles (one per voice) and slots (per
  language and text type). Every change is shown as a diff first and can be rolled back.
- **Write and rewrite** from the learned profile and a few real example passages, without inventing
  facts.
- **Check** a draft against the writer's measured style, flagging both too little and too much of a
  habit.
- **Prove itself** in blind tests against a plain draft and against a draft given the same examples.

## Repository layout

```
docs/          design document, diagrams and their editable sources
idiolect/      the skill itself (SKILL.md, scripts, references, assets) — packaged as idiolect.skill
evals/         evaluation protocol, fixture texts, edit pairs, experiments — not shipped with the skill
```

## Design

The full design is in [docs/design.md](docs/design.md). Start with the architecture:

![Idiolect architecture](docs/idiolect-design-images/01-architecture.png)

## Build plan

| Phase | What |
| --- | --- |
| 0 | Groundwork: schemas, rules, fixtures, metric experiment, evaluation protocol |
| 1 | Engine: store discovery, inventory, ledger, adapters, measurement |
| 2 | Learning: lessons, approval, snapshots, rollback |
| 3 | Writing: write, rewrite, check, evaluation |
| 4 | Validation: `test` |
| 5 | Feedback: learn-edit, interview, more facets, inheritance |
| 6 | Reach: cloud route, export, more adapters, use from other skills |

## Licence

MIT, see [LICENSE](LICENSE).
