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
| Holdout | Per author, whole essays set aside before learning with a fixed seed (`evals/holdouts.json`) and excluded by the folder rules, so they never enter the store. Synthetic authors: 5 of 12 essays. Public-domain authors: 3 essays |
| Test passages | 300–500-word passages cut at paragraph boundaries from holdout essays by `evals/harness.py passages` (fixed seed); **at least 10 per author**, so at least 20 for the synthetic group and 40 for the public-domain group per run |
| Profiles | Built by `learn` on the remaining essays of each author, approved without edits (`evals/store/`) |

## Roles

1. **Brief writer** (fresh agent). Reads one test passage and writes a brief of at most 60 words: the
   subject and up to three points, in its own words, plus the target length. A script rejects the
   brief if it shares any run of four or more words with the passage (ignoring stop words), and it is
   rewritten.
2. **Generators** (three fresh agents per brief, none of which ever sees a test passage, a holdout
   essay or its path):
   - **Plain**: the brief only. "Write this."
   - **Few-shot**: the brief plus the same three example passages Idiolect's `write` would load for
     this brief (chosen by the same script from the author's example bank, which holds learned texts
     only), with "write in the style of these passages".
   - **Idiolect**: `/idiolect write` with the brief, the author's profile, `interactive=false`.
   - **Same footing.** All three use the same model, the same instruction skeleton ("Write a piece of
     about N words from this brief. Do not add facts, names or anecdotes that are not in the brief;
     leave a placeholder instead."), and target the passage's length ±15%. A draft outside that range
     is regenerated once; if it is still outside, it is kept and its length reported.
   - **Isolation.** Generators run in a scratch folder outside the repository. The Idiolect
     generator gets a copy of the store with only `idiolect.yaml` and `profiles/` (no corpus, no
     sources); the few-shot generator gets only its three passages. Each is told to read nothing
     else, and its transcript is kept in the run folder so a leak can be checked afterwards.
3. **Shuffler** (script). Labels the three drafts A, B, C at random and stores the key in
   `evals/runs/<run-id>/key.json`, which no judge sees.
4. **Judge** (fresh agent, following `evals/judge.md`: skill-creator's blind-comparator rules with a
   style rubric instead of a task rubric). Sees the test passage and drafts A, B, C. Ranks all three
   (no ties) by how closely they read as written by the passage's author, with one line per draft on
   why. It is told to ignore content and judge voice.
5. **Recognition check** (a separate fresh agent per passage, which sees the passage only): "Do you
   recognise the author of this passage? Name and confidence (none, low, medium, high)." Its answer
   is saved in the run folder; it never sees drafts, and the judge never sees its answer.
6. **Spot-checker** (a person). Reviews a random 10% of judgments, at least one per author, and marks
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

For each group, over all its briefs, **in each of the two runs**:

| Comparison | Idiolect must win at least |
| --- | --- |
| vs plain | 70% |
| vs few-shot | 60% |

And no single author below 50% against few-shot. In addition, pooled over the two runs, each
comparison must beat chance: a one-sided exact binomial test against 50% gives p < 0.05 (for 40
briefs that means at least 26 wins; for 80, at least 49). The binomial check guards against a small
group passing by luck; the per-run bar guards against one lucky run.

If the few-shot bar is missed, the design changes before more is built (phase 3 is not done).

## Runs and results

- A run lives in `evals/runs/<run-id>/` (`run-id` = UTC timestamp `YYYYMMDDTHHMMSSZ`): passages,
  briefs, drafts, generator transcripts, `key.json`, judgments, recognition answers, spot-checks, and
  `results.md`. `evals/harness.py` prepares, shuffles and scores; agents do the rest.
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
