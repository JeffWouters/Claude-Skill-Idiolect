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
| Authors | All fixture authors in `evals/fixtures/` (from run 2: 3 public-domain, 2 synthetic), each screened per passage before use (`evals/fixtures/README.md`) |
| Holdout | Per author, whole essays set aside before learning with a fixed seed (`evals/holdouts.json`) and excluded by the folder rules, so they never enter the store. Synthetic authors: 5 of 12 essays. Public-domain authors: 3 essays |
| Test passages | 300–500-word passages cut at paragraph boundaries from holdout essays by `evals/harness.py new` (fixed seed; the seed also moves where the first passage of each essay starts, and passages used by earlier runs named with `--avoid` are taken last); **10 per author, or as many as the holdout essays give** (non-overlapping, never padded). Run 1 had 10 for every author except Alice Meynell, whose short holdout essays gave 7 |
| Profiles | Built by `learn` on the remaining essays of each author (`evals/store/`), approved without edits except proposals that are content rather than style (for example vocabulary that quotes another writer), which are rejected and listed in the profile's changelog |

## Roles

1. **Brief writer** (fresh agent). Reads one test passage and writes a brief of at most 60 words: the
   subject and up to three points, in its own words, plus the target length. A script rejects the
   brief if it shares any run of four or more words with the passage (ignoring stop words), and it is
   rewritten.
2. **Generators** (one fresh agent per author and kind, writing that author's briefs in turn; none
   ever sees a test passage, a holdout essay or its path):
   - **Plain**: the brief only. "Write this."
   - **Few-shot**: the brief plus the same three example passages Idiolect's `write` would load for
     this brief (chosen by the same script from the author's example bank, which holds learned texts
     only), with "write in the style of these passages".
   - **Idiolect**: `/idiolect write` with the brief, the author's profile, `interactive=false`.
   - **Same footing.** All three use the same model, the same instruction skeleton ("Write a piece of
     about N words from this brief. Do not add facts, names or anecdotes that are not in the brief;
     leave a placeholder instead."), and target the passage's length ±15%. A draft outside that range
     is regenerated once; if it is still outside, it is kept and its length reported.
   - **Isolation.** Generators run in a scratch folder outside the repository, and authors are
     anonymised there (w1, w2, ...). The Idiolect generator gets a copy of the store with only
     `idiolect.yaml` and `profiles/` (no corpus, no sources); the few-shot generator gets only its
     three passages. Each generator has **its own working folder** for anything it saves (run 1's
     generators shared one and overwrote each other's files). Each is told to read nothing else,
     and keeps a log of every file it opened, stored in the run folder so a leak can be checked.
3. **Shuffler** (script). Labels the three drafts A, B, C at random and stores the key in
   `evals/runs/<run-id>/key.json`, which no judge sees.
4. **Judge** (a fresh agent per packet, following `evals/judge.md`; packets carry anonymous ids and
   runs of spaces are collapsed, so neither a name nor typography identifies a draft: skill-creator's blind-comparator rules with a
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
briefs that means at least 26 wins; for 80, at least 48). A passage that appears in more than one run counts once in the pool. The binomial check guards against a small
group passing by luck; the per-run bar guards against one lucky run.

If the few-shot bar is missed, the design changes before more is built (phase 3 is not done).

## Runs and results

- A run lives in `evals/runs/<run-id>/` (`run-id` = UTC timestamp `YYYYMMDDTHHMMSSZ`): passages,
  briefs, drafts, generator transcripts, `key.json`, judgments, recognition answers, spot-checks, and
  `results.md`. `evals/harness.py` prepares, shuffles and scores; agents do the rest.
- `results.md` has one row per author (briefs, excluded for recognition, win rate vs plain, vs
  few-shot, mean flags per draft type) and one row per group with pass or fail.
- No single "voice score" is produced.

## Run 4: a diagnostic run (after the review of runs 1 to 3)

Runs 2 and 3 shared 38 of their 50 passages and one agent wrote all of an author's drafts per arm, so
they were not the two independent runs the bar needs. Run 4 is one diagnostic run, set up to show
**which part of Idiolect helps or hurts**, not to pass or fail the phase on its own:

- **Four arms**: plain, few-shot, Idiolect (full write), and **lite**: the same kit without the
  measurable targets and without the check-and-revise loop (`evals/ablation/write-lite.md`,
  `kit.py --omit targets`). Idiolect against lite isolates targets plus loop; lite against few-shot
  isolates the lessons, phrases and forms.
- **Several generators per author**: each author's briefs are split into blocks of four, one agent
  per block and arm (`prepare --per-agent 4`), and win rates get 95% intervals from resampling
  agents, not briefs.
- **Balanced labels**: every arm sits at every label equally often. **Typography normalised**: one
  glyph each for quotes, apostrophes, dashes and spaces in passage and drafts alike.
- **Prompts live in the scratch folder**, generated by `prepare`, and name no author; the store copy
  drops the consent and subject lines.
- Recognition checks run for every real-author passage; the results say "not run" where they were not.
- 8 briefs per author (40 in all). The synthetic authors' and Holliday's holdout essays give only 10
  or 11 passages, so some of run 4's passages repeat earlier runs; `run.json` records how many.

## Runs 5 and 6: confirming runs (after the decision on run 4)

The design changed after run 4 (design: decision log): observed lessons are background in the kit,
and targets follow the piece. Runs 5 and 6 test that design and count towards the bar.

- **Fresh text only.** Every passage is cut from held-out text no earlier run used, checked per
  paragraph (`new --source later --fresh-only --avoid <runs 1 to 4, and run 5 for run 6>`). The
  `later` source (`evals/holdouts.json`, folder `evals/holdouts-later/`):
  - Holliday: *Turns about Town* (1921); Crothers: *Humanly Speaking* (1912). Other essay books by
    the same authors, never learned, so passages test the voice beyond the book it was learned from.
  - Gerould has no other essay book on Project Gutenberg; the unused paragraphs of her three held-out
    essays give 7 fresh passages in all: 4 in run 5 and 3 in run 6.
  - Noor and Idris: 12 new essays each, never learned, written by fresh agents that saw only a style
    specification (`SPEC.md` in their folder). The original specs were not kept, so the
    specifications were reconstructed from the 12 fixture essays by a separate agent. `check` reads
    them as the authors' own: none fails against its author (0 to 3 flags, against 0 to 3 for the
    original holdouts), and against the other synthetic author they get 9 to 10 flags. They are still
    model-written from a written description, which may favour whichever arm writes most like such a
    description; this is recorded as a caveat, not corrected for.
- **Passages per author**: 10 for Holliday and Crothers, 8 for each synthetic author, 4 and 3 for
  Gerould (`--per-author 10 --cap katharine-fullerton-gerould=4 --cap synthetic-idris=8 --cap
  synthetic-noor=8`).
- **Arms**: plain, few-shot, Idiolect (the new default kit) and **bare**: the same procedure with
  `kit.py --notes none`, no observed lessons (`evals/ablation/write-bare.md`). Idiolect against bare
  shows whether the background notes still help or hurt.
- Everything else as in run 4: four drafts per packet, balanced labels, normalised typography, four
  briefs per generator agent, agent-resampled intervals, a recognition check on every real-author
  passage, and a spot-check for a person.

## Repeatability

Fixed seeds for holdout selection, passage cuts and label shuffling (`evals/runs/<run-id>/seed`).
Generators and judges are model calls and vary; a phase is only marked done on a pass that holds over
**two separate runs**.

## A writer's own profile (after phase 3)

The same protocol with three changes: the writer picks the holdout texts (at least 5), the writer is
the judge (drafts labelled A/B/C, key hidden), and there are no groups. Results go in the store's
`eval/results.md`.
