# Claude-Skill-Idiolect — working notes for Claude

This repository holds the source of the **Idiolect** skill. Read `docs/design.md` before changing
anything; it is the single source of truth for behaviour, file formats and the build plan.

## Current phase

**Phase 0: groundwork.** Deliverables and where they live:

| Deliverable | Location |
| --- | --- |
| Schemas for every store file and the check report | `idiolect/assets/schemas/` |
| Rules specification (ownership, hashing, manifest lifecycle, pending area, lock, deletion, edge cases) | `docs/spec.md` |
| Fixture authors and scripted edit pairs | `evals/fixtures/`, `evals/edit-pairs/` |
| Metric experiment and the chosen global metric list | `evals/spike/` |
| Evaluation protocol | `evals/eval-protocol.md` |

Phase 1 does not start until all of these exist and have been reviewed.

## Rules for working here

- **The design wins.** If code and `docs/design.md` disagree, either the code is wrong or the design
  needs a decision-log entry first. Never let them drift silently.
- **No real people in the package.** Nothing under `idiolect/` may contain a real person's name,
  text, employer or phrasing. Real texts live only in `evals/fixtures/` and are public domain.
- **Generic core.** The skill holds no writer data. Examples use the fictional writer Sam, the
  company Acme and the house style `house`.
- **Schemas are versioned.** Any change to a store file format bumps `schema_version` and ships with
  a migration.
- **Commit per change**, with a message that says what behaviour changed and why.
- **Never delete.** Move retired material to `_to_delete/` and say so.
- **Package, don't install.** A session cannot save a skill to an account. Build `idiolect.skill`
  from the `idiolect/` folder and deliver it; never report it as saved.
