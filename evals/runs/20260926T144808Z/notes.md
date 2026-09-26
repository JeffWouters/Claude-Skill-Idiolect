# Runs 20260926T144759Z (run 2) and 20260926T144808Z (run 3): notes

Both runs used the design after run 1's changes: example passages first in the kit, lessons with
"seen in N of M texts", habits sampled rather than stacked, forms separated from favoured phrases
with measured rates, bunched-habit flags in `check`, and screened authors (Robert Cortes Holliday
and Katharine Fullerton Gerould in place of three recognisable authors). Each generator had its own
working folder; each packet had its own fresh judge.

## Outcome

**The few-shot bar is missed in both runs, in both groups. Phase 3 is not done.**

| Run | Idiolect vs plain | Idiolect vs few-shot | Real group vs few-shot | Synthetic group vs few-shot |
| --- | --- | --- | --- | --- |
| 1 (old design) | 53 of 57 | 24 of 57 (42%) | 12 of 37 | 12 of 20 |
| 2 | 50 of 50 | 28 of 50 (56%) | 17 of 30 (57%) | 11 of 20 (55%) |
| 3 | 50 of 50 | 18 of 50 (36%) | 11 of 30 (37%) | 7 of 20 (35%) |

Pooled over runs 2 and 3, Idiolect beats few-shot in 46 of 100 briefs; the one-sided binomial test
gives p = 0.74 (real) and 0.79 (synthetic), so there is no evidence that Idiolect does better than
few-shot at all. Against plain it wins every brief.

`check` sees the opposite: Idiolect drafts average 0.9 and 0.6 flagged metrics and none fails, against
3.2 and 2.6 for few-shot (32 fails over the two runs) and 4.7 and 4.4 for plain (61 fails). The drafts
match the fingerprint; the judges still prefer few-shot.

## Recognition checks were not run

The protocol excludes briefs whose passage a separate agent recognises. That exclusion only touches
real-author briefs, and the synthetic group fails in both runs on its own, so no recognition result
could change the outcome. The per-passage checks were skipped to save about a hundred agent runs; the
results above count every brief. They can still be run with the same prompts if a record is wanted.

## What the judges say

Two patterns account for most of the losses.

1. **Caricature, still, for the synthetic author with the strongest habits.** In run 3 few-shot beat
   Idiolect in 9 of 10 briefs for synthetic-noor (clipped sentences, fragments). Nearly every reason
   is the same: the Idiolect draft "stacks fragments more thickly than the passage", adds signposting
   ("Here is the routine.", "First the clock.") and aphoristic closers ("Not speed. Attention."). The
   kit's framing reduced this for the other synthetic author but not here: the habit that defines the
   writer is exactly the one the model over-applies.
2. **Averaging, for a real author whose texts vary.** In run 3 few-shot beat Idiolect in 9 of 10 briefs
   for Robert Cortes Holliday. The passages are clipped, anecdotal, full of fragments and overheard
   speech; the Idiolect drafts are "long, balanced, semicolon-laden periodic sentences", "a composed
   essay rather than the passage's clipped snapshots". The fingerprint, lessons and targets describe
   the writer's average essay; a passage is one mode of it, and the few-shot draft, with only three
   passages chosen for the topic, lands closer to that mode.

## What this says about the design

The few-shot baseline is not "Claude plus any three passages". It uses Idiolect's own approved,
redacted example bank and Idiolect's own script to pick the passages; with banks of 4 to 6 examples,
that is most of the bank. So the comparison is **Idiolect's examples alone** against **Idiolect's
examples plus lessons, forms, targets, the check-and-revise loop and a longer procedure**.

What the data supports: **no evidence that the additions help** (46 of 100 against few-shot, 95%
interval roughly 36 to 56%, wider once the caveats below are counted). What it does not support: that
they add *nothing*, or which part hurts. The effect varies by author (pooled over runs 2 and 3:
Crothers and synthetic-idris 12 of 20, Gerould 10 of 20, Holliday and synthetic-noor 6 of 20), and no
arm isolates the lessons, the targets or the revise loop. One measured sign for Holliday: his profile
targets 7.3 semicolons per 1,000 words, his held-out passages have 3.6, and Idiolect drafts land at
7.1 to 7.8 against few-shot's 3.5 to 4.4, which fits "the targets pull drafts towards the corpus
average".

That is a design question for the writer (design: "Missing the few-shot bar means the machinery adds
nothing, and the design changes"); it is set out in the report, not decided here.

## Caveats found in the independent review

- **Runs 2 and 3 are not independent samples.** 38 of their 50 passages are identical: the holdout
  essays of the synthetic authors and Holliday give only 10 or 11 passages, and `cut()` ignores its
  seed. Run 3 is closer to a regeneration of run 2 than a new run, and the pooled binomial treats
  100 briefs as independent when there are 62 distinct passages.
- **Generator batches matter more than passages.** On the 38 shared passages the Idiolect-vs-few-shot
  outcome agreed between runs only 22 times; synthetic-noor went from 5 of 10 to 1 of 10 and Holliday
  from 5 of 10 to 1 of 10 on the same passages. One agent writes all ten briefs per author and kind,
  so per-author rates are single draws and the p-values are too optimistic.
- **Typography differs by arm.** Passages use "—" or "--"; few-shot drafts copy them, Idiolect drafts
  for Idris and Holliday use none. Part of that is voice (Idiolect drops the device), part a
  typographic tell the judge packets do not normalise.
- **Position bias in run 2:** the later label won the Idiolect-vs-few-shot pair 33 of 50 times
  (p = 0.03); not in runs 1 and 3. Labels are random, so this adds noise, not direction.
- **The spot-check is not done**, so no run counts yet; `results.md` shows "0 excluded" where
  recognition checks were simply not run.

## Process

- 10 brief writers, 30 generators (one per author and kind per run, each with a private folder), 100
  judges. No generator reported a leak or a shared-file clash.
- The overlap check found no brief sharing a four-word run with its passage; every draft was within
  15% of its target length.
- Spot-check sheets for a person: `spotcheck.md` in each run folder (5 judgments per run, at least one
  per author). Not yet marked.
