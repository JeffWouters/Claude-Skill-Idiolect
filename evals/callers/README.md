# Calls from other skills (phase 6 exit, first part)

`publish-demo/` is a stand-in publishing skill: it runs Idiolect's `check` non-interactively through
`scripts/gate.py` and publishes a draft only on `pass` or `low_confidence` (spec §25). It never asks
Idiolect a question and never writes to the store.

- `tests/test_callers.py`: the writer's own held-out passage is published, a plain draft is blocked
  with its flagged metrics, and a missing store or profile stops without publishing.
- **Live run, 2026-09-26.** A scratch project had `idiolect` and `publish-demo` in `.claude/skills/`,
  a copy of `evals/store`, and two drafts (a held-out synthetic-noor passage from run 6, and the plain
  arm's draft for the same brief). `claude -p "Publish drafts/<f>.md with publish-demo. The Idiolect store
  is ./store and the profile is synthetic-noor."` (claude-opus-5-5):
  - own passage: publish-demo loaded, ran the gate; **published** (`pass`, 3 metrics flagged, fails at 4).
  - plain draft: **not published** (`fail`); the reply listed the overshoots and suggested revising or
    asking Idiolect to rewrite.
