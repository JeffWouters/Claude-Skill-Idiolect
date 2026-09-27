# Claude-Skill-Idiolect — working notes for Claude

This repository holds the source of the **Idiolect** skill. Read `docs/design.md` before changing
anything; it is the single source of truth for behaviour, file formats and the build plan.

## Current phase

**All build phases (0 to 6) are done.** Scripts in `idiolect/scripts/`, model procedures in
`idiolect/references/modes/`, tests in `tests/`, the learned evaluation store in `evals/store/`
(holdouts in `evals/holdouts.json`). Phase 3 (write, rewrite,
check, the kit and the evaluation harness) was closed by the writer on the synthetic result (runs 5
and 6); the real authors are the known-author group, reported but not gating, and the check uses
writer bands (design: decision log). Phase 4 added the `test` mode (`scripts/holdout.py`,
`references/modes/test.md`, spec §19), the drift exit tests and the trigger tests (`evals/triggers/`,
run serially). The writer's own blind test is `test judge=true` and waits for the writer's texts.
Phase 5 added `learn-edit` (`scripts/learn_edit.py`, spec §20), `interview` (`scripts/interview.py`, §21),
the mail adapter (§6.4), `migrate.py --add-facet` (§12.7) and the marking of rulings from profiles not
the writer's own (§12.6). Phase 6 added `export` (§22), web and connector texts (`web.py`, `connector.py`, §23), transcripts
(§24), calls from other skills (`evals/callers/`, §25) and the bridged route (`runtime.md`, `bridge.py`,
§26). Short mails are joined per thread, then per week (spec §6.4). After phase 6: rulings schema v2
with tests, `rules.py` (`defaults`, `add`, `show`), the optional starter set
`idiolect/assets/starter-rules/en.yaml` and `references/modes/rules.md` (spec §27); `check` fails a
draft that breaks a ruling. Then: outliers at learn and `verify.py` (§28, threshold from `evals/outliers/`),
`guide.py` (§29), `rules.py guide-text`/`import` (§30) and `tone=` in `kit.py`/`check.py` (§31). Then: language packs (`references/lang/<code>/pack.yaml`,
`langpack.py`, Dutch with `starter-rules/nl.yaml`, fixture `synthetic-sanne`, §32) and `published.py`
(kept drafts, scan, edit queue, §33). Open: the writer's own blind test (`test judge=true`). Recognition from run 7 is forced choice with controls and a sensitivity test
(`evals/recognition-study/`).
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
  repository URL in schema `$id` values and in the plugin manifest names the repository, not a
  writer, and is allowed.
- **Generic core.** The skill holds no writer data. Examples use the fictional writer Sam, the
  company Acme and the house style `house`.
- **Schemas are versioned.** Any change to a store file format bumps `schema_version` and ships with
  a migration.
- **Commit per change**, with a message that says what behaviour changed and why.
- **Never delete.** Move retired material to `_to_delete/` and say so.
- **Release.** Bump `version` in `idiolect/.claude-plugin/plugin.json`, add its entry to `CHANGELOG.md`,
  commit, then push a tag `vX.Y.Z`; the release workflow tests, builds and publishes `idiolect.skill`.
- **Package, don't install.** A session cannot save a skill to an account. Build `idiolect.skill`
  from the `idiolect/` folder and deliver it; never report it as saved.
