# Claude-Skill-Idiolect — working notes for Claude

This repository holds the source of the **Idiolect** skill. Read `docs/design.md` before changing
anything; it is the single source of truth for behaviour, file formats and the build plan.

## Current phase

**Phases 1 (engine) and 2 (learning) are done.** Scripts in `idiolect/scripts/`, model procedures in
`idiolect/references/modes/`, tests in `tests/`, the learned evaluation store in `evals/store/`
(holdouts in `evals/holdouts.json`). **Phase 3 (writing) is built but not done:** write, rewrite,
check, the kit and the evaluation harness exist, and three evaluation runs (`evals/runs/`) missed the
few-shot bar. The design decision that follows is the writer's; see the latest run's `notes.md`.
Run `python3 -m pytest tests -q` before every commit.

Phase 0 deliverables, still the reference:

| Deliverable | Location |
| --- | --- |
| Schemas for every store file and the check report | `idiolect/assets/schemas/` |
| Rules specification (ownership, hashing, manifest lifecycle, pending area, lock, deletion, edge cases) | `docs/spec.md` |
| Fixture authors and scripted edit pairs | `evals/fixtures/`, `evals/edit-pairs/` |
| Metric experiment and the chosen global metric list | `evals/spike/` |
| Evaluation protocol | `evals/eval-protocol.md` |
| Metric definitions and English word lists | `idiolect/references/fingerprint.md`, `idiolect/references/lang/en/` |
| Inventory fixture with its expected report (phase 1's exit test) | `tests/inventory-fixture/` |

Reviewed twice before phase 1 started.

## Rules for working here

- **The design wins.** If code and `docs/design.md` disagree, either the code is wrong or the design
  needs a decision-log entry first. Never let them drift silently.
- **No real people in the package.** Nothing under `idiolect/` may contain a real person's name,
  text, employer or phrasing. Real texts live only in `evals/fixtures/` and are public domain. The
  repository URL in schema `$id` values names the repository, not a writer, and is allowed.
- **Generic core.** The skill holds no writer data. Examples use the fictional writer Sam, the
  company Acme and the house style `house`.
- **Schemas are versioned.** Any change to a store file format bumps `schema_version` and ships with
  a migration.
- **Commit per change**, with a message that says what behaviour changed and why.
- **Never delete.** Move retired material to `_to_delete/` and say so.
- **Package, don't install.** A session cannot save a skill to an account. Build `idiolect.skill`
  from the `idiolect/` folder and deliver it; never report it as saved.
