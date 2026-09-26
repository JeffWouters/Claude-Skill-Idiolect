# Evaluation protocol (v1)

How Idiolect is judged. Written before any evaluation runs; changing it after results are in needs a
decision-log entry in `docs/design.md`.

## Question

Does a draft written by Idiolect from a writer's profile read more like that writer than
(a) a plain Claude draft and (b) a Claude draft given the same example passages but no profile?

(b) is the question that matters. If Idiolect cannot beat "Claude plus three of your passages", the
profile machinery adds nothing.

## Where it runs

Claude Code or Cowork, where separate agents can be started. Every generating and judging role below
is a **fresh agent**. The tester switches off every other voice or writing-style skill for the whole
run, because agents inherit enabled skills.

## Materials

| Item | Rule |
| --- | --- |
| Authors | All fixture authors in `evals/fixtures/` (currently 4 public-domain, 2 synthetic) |
| Holdout | Per author, whole essays set aside before learning, flagged `holdout: true` in the store's manifest. Synthetic authors: 5 of 12 essays. Public-domain authors: 3 essays |
| Test passages | 300–500-word passages cut at paragraph boundaries from holdout essays; **at least 10 per author** |
| Profiles | Built by `learn` on the remaining essays of each author, approved without edits |

## Roles

1. **Brief writer** (fresh agent). Reads one test passage and writes a brief of at most 60 words: the
   subject and up to three points, in its own words, plus the target length. A script rejects the
   brief if it shares any run of four or more words with the passage (ignoring stop words), and it is
   rewritten.
2. **Generators** (three fresh agents per brief, none of which ever sees a test passage, a holdout
   essay or its path):
   - **Plain**: the brief only. "Write this."
   - **Few-shot**: the brief plus the same three example passages Idiolect's `sample.py` would pick
     for this topic, with "write in the style of these passages".
   - **Idiolect**: `/idiolect write` with the brief, the author's profile, `interactive=false`.
   All three target the passage's length ±15%.
3. **Shuffler** (script). Labels the three drafts A, B, C at random and stores the key in
   `evals/runs/<run-id>/key.json`, which no judge sees.
4. **Judge** (fresh agent, using skill-creator's comparator instructions). Sees the test passage and
   drafts A, B, C. Ranks the drafts by how closely they read as written by the passage's author, and
   gives one line per draft on why. Then answers separately: "Do you recognise the author of the
   passage? Name and confidence."
5. **Spot-checker** (a person). Reviews a random 10% of judgments, at least one per author, and marks
   each agree or disagree. More than 20% disagreement invalidates the run.

## Scoring

- **Win against plain**: Idiolect ranked above the plain draft for that brief. Same for few-shot.
- **Win rate**: wins divided by briefs, computed per author and per group.
- **Groups**: synthetic authors and public-domain authors are scored **separately**. The model has a
  sense of the real authors' styles (phase 0 recognition check), which could flatter every draft that
  sees examples; the synthetic authors cannot be known from training but are more regular than real
  prose. Only passing in both groups counts.
- **Recognition**: a brief whose judge names the author with medium or higher confidence is reported
  but excluded from the win rates.
- **Metric drift**: every draft is also run through `check` against the author's fingerprint; flag
  counts are reported next to the blind picks. They inform, they do not decide.

## The bar

For each group, over all its briefs:

| Comparison | Idiolect must win at least |
| --- | --- |
| vs plain | 70% |
| vs few-shot | 60% |

And no single author below 50% against few-shot. If the few-shot bar is missed, the design changes
before more is built (phase 3 is not done).

## Runs and results

- A run lives in `evals/runs/<run-id>/` (`run-id` = UTC timestamp `YYYYMMDDTHHMMSSZ`): briefs, drafts,
  `key.json`, judgments, spot-checks, and `results.md`.
- `results.md` has one row per author (briefs, excluded for recognition, win rate vs plain, vs
  few-shot, mean flags per draft type) and one row per group with pass or fail.
- No single "voice score" is produced.

## Repeatability

Fixed seeds for holdout selection, passage cuts and label shuffling (`evals/runs/<run-id>/seed`).
Generators and judges are model calls and vary; a phase is only marked done on a pass that holds over
**two separate runs**.

## A writer's own profile (after phase 3)

The same protocol with three changes: the writer picks the holdout texts (at least 5), the writer is
the judge (drafts labelled A/B/C, key hidden), and there are no groups. Results go in the store's
`eval/results.md`.
