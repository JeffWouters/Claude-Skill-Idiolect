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

**Context.** Agents also inherit the session's memory of the person running it. In the recognition
study two agents answered "Jeff (JeffOps)" for synthetic passages: the tester's own profile had
reached them. Recognition, judging and screening agents are therefore run with memory switched off
where the surface allows it, and every prompt tells the agent to use no memory or notes about the
person it works for. A run that cannot switch memory off says so in its notes.

## Materials

| Item | Rule |
| --- | --- |
| Authors | All fixture authors in `evals/fixtures/` (from run 2: 3 public-domain, 2 synthetic), each screened per passage before use (`evals/fixtures/README.md`; from run 7 by forced choice, "Recognition (runs 7 on)") |
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
5. **Recognition check** (a separate fresh agent per passage, which sees the passage only). From run 7:
   **forced choice**. The agent gets ten writers (the true author and nine distractors, or ten
   distractors for a synthetic passage) and "none of these", and gives a probability to each; the
   probability on the true author is the passage's **familiarity** (details under "Recognition (runs 7
   on)"). Runs 1 to 6 asked "Do you recognise the author of this passage? Name and confidence (none,
   low, medium, high)." Either way the answer is saved in the run folder; the agent never sees drafts,
   and the judge never sees its answer.
6. **Spot-checker** (a person). Reviews a random 10% of judgments, at least one per author, and marks
   each agree or disagree. More than 20% disagreement invalidates the run.

## Scoring

- **Win against plain**: Idiolect ranked above the plain draft for that brief. Same for few-shot.
- **Win rate**: wins divided by briefs, computed per author and per group.
- **Groups**: scored **separately**. Only the unknown-author tests decide phase 3 (see "The bar"); the
  known-author group is scored and reported every run.
  - The **known-author group** (the public-domain authors, `real` in the data). The model knows these
    writers: in the recognition study a forced-choice agent put the true author first for all twelve
    real passages tried, most of them passages from books it had never been shown. So this group tests
    Idiolect on writers the model already has a picture of, and its result is read beside familiarity
    and the sensitivity test.
  - The **unknown-author tests**: the synthetic authors (`synthetic` in the data), whom no model can
    know from training, and, after phase 3, the writer's own profile. These are the tests of learning a
    voice the model does not already hold. Synthetic authors are more regular than real prose, so they
    cannot stand in for the known-author group either.
- **Recognition**, runs 7 on: **no brief is excluded.** Every brief counts towards the bar, and the
  results show win rates by familiarity (under 30%, 30 to 59%, 60% or more) beside it. Runs 1 to 6
  excluded briefs recognised at medium or high confidence, and keep that.
- **Sensitivity test**, runs 7 on: a seeded sample of 12 known-author packets is judged again by
  fresh judges, once blind and once told the author's name. If naming the author moves Idiolect's wins
  over few-shot by at least max(3, a quarter of the sample), the known-author result of that run is
  marked **unreliable**: the judges are then reading the author's reputation more than the passage.
  An unreliable run cannot count as a known-author pass.
- **Detector check**, runs 7 on: the positive control must get at least 60% on its author, and the
  synthetic passages (the negative controls) must average at least 80% on "none". If either fails,
  the familiarity figures of that run are not trusted and the run says so.
- **Metric drift**: every draft is also run through `check` against the author's fingerprint; flag
  counts are reported next to the blind picks. They inform, they do not decide.

## The bar

**The unknown-author tests decide phase 3**: the synthetic authors and the writer's own profile. The
known-author group is held to the same numbers in every report, but missing them does not stop the
phase (design: decision log, after runs 5 and 6): the model knows those writers, so their result
measures its prior as much as Idiolect. `harness.py pool` reports `bar_met` from the gating groups.

For each gating group, over all its briefs, **in each of the two runs**:

| Comparison | Idiolect must win at least |
| --- | --- |
| vs plain | 70% |
| vs few-shot | 60% |

And no single author below 50% against few-shot. "All its briefs" means all: from run 7 no brief is
left out for recognition, and a known-author result the sensitivity test marks unreliable does not
count as a pass. In addition, pooled over the two runs, each
comparison must beat chance: a one-sided exact binomial test against 50% gives p < 0.05 (for 40
briefs that means at least 26 wins; for 80, at least 48). A passage that appears in more than one run counts once in the pool. The binomial check guards against a small
group passing by luck; the per-run bar guards against one lucky run.

If the few-shot bar is missed on an unknown-author test, the design changes before more is built
(phase 3 is not done). The synthetic group met the bar in runs 5 and 6; the design change after
those runs (writer bands) leaves every synthetic kit and check report unchanged, so that result
stands. The writer's own test is the deciding test.

## Runs and results

- A run lives in `evals/runs/<run-id>/` (`run-id` = UTC timestamp `YYYYMMDDTHHMMSSZ`): passages,
  briefs, drafts, generator transcripts, `key.json`, judgments, recognition answers, spot-checks, and
  `results.md`. `evals/harness.py` prepares, shuffles and scores; agents do the rest.
- `results.md` has one row per author (briefs, mean familiarity (runs 1 to 6: excluded for
  recognition), win rate vs plain, vs few-shot, mean flags per draft type), one row per group with
  pass or fail, and from run 7 the win rates by familiarity, the detector check and the sensitivity
  test.
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

## Recognition (runs 7 on)

Decided after the recognition study (`evals/recognition-study/`, design: decision log). The confidence
label of runs 1 to 6 did not measure familiarity: agents named the right author at "low" confidence
59 times, and forced choice put the true author first for every real passage tried.

- **Forced choice.** `harness.py recognition --run R --scratch DIR` writes one prompt
  (`evals/prompts/recognition.txt`) per passage: ten writers in alphabetical order and "none", each
  given a probability, adding up to 100. The candidates are the true author plus nine distractors
  drawn by seed from `evals/recognition-candidates.json` (essayists of the same period and kind, so
  the true author does not stand out); a synthetic passage gets ten distractors. One fresh agent per
  prompt, which reads the passage only. Answers go back with `import-judge`, which rejects an answer
  that does not name exactly the candidates or does not add up to 100 (within 5).
- **Controls, every run.** A **positive control**: a passage by a well-known writer (Charles Lamb,
  the opening of "Dream-Children", `evals/recognition-controls/`), asked the same way under the same
  kind of shuffled id, so the agent cannot tell it from a test passage. **Negative controls**: the
  synthetic passages, whose right answer is "none". Both are checked by the detector check.
- **Sensitivity test.** After `export-judge`, `harness.py sensitivity --run R --scratch DIR [--n 12]`
  writes a blind and an author-named prompt (`sens-blind.txt`, `sens-named.txt`) for a seeded sample
  of known-author packets; one fresh judge per prompt. `score` reports the wins over few-shot of the
  original, blind and named judgments, their agreement with the original, and the flag.
- **Name redaction is not a fix.** In the study, removing names and dates from passages changed
  nothing: the model knows these writers by their prose. Passages are not redacted for judging.
- **Screening a new author.** `harness.py screen --scratch DIR --name "<author>" --files <at least
  four ~300-word passages, names and dates removed>` writes forced-choice prompts for the passages and
  the positive control; after the agents answer, `harness.py screen --scratch DIR` reports the
  probability on the true author per passage. The author is usable when the mean is **under 30%** and
  the positive control works. Obscure non-literary writers (diarists, local journalists, letter
  writers, trade writers) are a better pool than the essay canon, which the model has read.

## Repeatability

Fixed seeds for holdout selection, passage cuts and label shuffling (`evals/runs/<run-id>/seed`).
Generators and judges are model calls and vary; a phase is only marked done on a pass that holds over
**two separate runs**.

## A writer's own profile

Decided after runs 5 and 6 as the deciding test for phase 3; the writer then closed phase 3 on the
synthetic result, and this test moved to phase 4 (design: decision log). The same protocol with
these changes:

- **Holdout.** The writer picks at least 5 of their own texts of the kind the profile covers, enough
  for **at least 20 passages** of 300 to 500 words. They are set aside as holdouts before the profile
  is learned (or the profile is relearned without them), so the profile never saw them.
- **One profile, no groups.** Arms: plain, few-shot, Idiolect. Briefs by fresh agents as usual.
- **Memory off for every agent.** Brief writers, generators and any agent helpers run with the
  writer's memory switched off (see "Context"): a plain generator that has the writer's profile in
  memory is not a plain baseline.
- **The writer judges.** Packets show the passage and the three drafts labelled A, B, C, the key
  hidden, in a balanced label order. The writer ranks all three per packet by "which reads most like
  me", ignoring content, and may add a line per draft. No spot-check: the writer is the judge.
- **The bar:** Idiolect ranked above plain in at least 70% of the briefs and above few-shot in at
  least 60%, over all of them, with the one-sided binomial p against 50% reported beside each. One
  run is enough, because a second set of the writer's own unseen texts is rarely available; that is
  why it needs 20 briefs rather than 10.
- Results go in the store's `eval/results.md` and are summarised in the design's decision log. A miss
  on few-shot means the design changes, as for any unknown-author test.

From phase 4 the skill runs this test itself: `test judge=true` holds out one text at a time
(`idiolect/references/modes/test.md`, spec §19), makes the three drafts where the text was never seen,
shows the writer a blind packet and records the ranking in `eval/results.md`. Twenty such tests, one
text each, make the run above; the harness is not needed for a writer's own profile.
