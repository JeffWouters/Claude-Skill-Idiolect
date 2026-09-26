# Run 20260926T154434Z (run 4, diagnostic): notes

Run 4 was set up after the review of runs 1 to 3 (`eval-protocol.md`, "Run 4: a diagnostic run"). It
has four arms (plain, few-shot, Idiolect, and **lite**: the same kit without measurable targets and
without the check-and-revise loop), two generator agents per author and arm, balanced labels,
normalised typography, and recognition checks on every real-author passage. It is meant to show which
part of Idiolect helps or hurts, not to pass the phase on its own.

## Outcome

Counted briefs exclude the 5 real-author passages a separate agent recognised at medium confidence
(35 of 40 counted). Win rate = share of briefs in which the judge ranked the first arm above the
second; intervals resample generator agents; p is a one-sided binomial test against 50%.

| Comparison | All (35) | Real (19) | Synthetic (16) |
| --- | --- | --- | --- |
| Idiolect vs plain | 35/35 | 19/19 | 16/16 |
| **Idiolect vs few-shot** | **22/35, 63% (51 to 72%), p = 0.09** | 11/19, 58% | 11/16, 69% |
| Lite vs few-shot | 18/35, 51% (33 to 69%), p = 0.5 | 10/19 | 8/16 |
| **Idiolect vs lite** | **24/35, 69% (56 to 79%), p = 0.02** | 11/19, 58% | 13/16, 81%, p = 0.01 |

Mean rank (1 is best): Idiolect 1.69, few-shot 2.14, lite 2.17, plain 4.00. Idiolect was ranked first
in 19 of 35 briefs, few-shot in 9, lite in 7. First place by label is flat (A 10, B 7, C 12, D 11).

By the protocol's bar this run passes for the synthetic group (69% against few-shot, bar 60%) and
misses for the real group by one brief (58%). One run cannot mark the phase done; two are needed.

## What the ablation says

1. **Lessons, favoured phrases and forms add nothing measurable over the examples.** Lite (examples
   plus lessons, phrases and forms, no targets, no loop) ties few-shot (examples alone): 18 of 35.
2. **The gain comes from the targets plus the check-and-revise loop.** Idiolect beats lite in 24 of
   35 briefs, 13 of 16 for the synthetic authors. This is the opposite of what runs 2 and 3 suggested
   ("the targets pull drafts towards the corpus average"), for four of the five authors.
3. **The averaging problem is real for one author.** For Robert Cortes Holliday lite beats Idiolect
   in 3 of 5 counted briefs. His held-out passages have 3.0 semicolons per 1,000 words; few-shot and
   lite drafts have 3.9 and 3.8, Idiolect drafts 7.3, close to the profile's target. For a writer
   whose texts vary, a single corpus-wide target pulls drafts away from the mode the brief calls for.
4. **Over-application is milder and has moved from fragments to hedges.** Read by hand, judges say an
   Idiolect draft lays a habit on thicker than the passage about 10 times, few-shot and lite drafts
   about 4 times each; most Idiolect mentions are "slight" and several are on drafts still ranked
   first. The recurring one is synthetic-idris, where drafts "stack hedges" ("it may be", "I suspect",
   "arguably", "it seems to me", "perhaps"). Synthetic-noor, the caricature case in run 3, now wins 6
   of 8 against few-shot.

## Why this run differs from runs 2 and 3

Runs 2 and 3 gave 56% and 36% against few-shot; this run gives 63%. The design did not change between
them; the evaluation did: four drafts per packet instead of three, normalised typography, balanced
labels, two generators per author instead of one, and fresh passages for Gerould and Crothers. The
review showed that runs 2 and 3 were dominated by generator batch effects (the same passages flipped
from 5 of 10 to 1 of 10). So this run does not show that Idiolect got better; it shows that under a
cleaner protocol the full design leads, and that the part doing the work is targets plus loop.

## Caveats

- **The recognition check understates how well the model knows these authors.** Only 5 of 24
  real-author passages were recognised at medium confidence (and excluded), but the recognition agents
  named the right author for 23 of 24, most of them at "low" confidence. The screening rule (at most
  one in four at medium or higher) is met, yet the judges may bring a sense of the real authors'
  styles. The synthetic group, which no model can know, is the cleaner signal, and it is the group
  where Idiolect's lead is clearest.
- **Some passages repeat earlier runs**: 14 of 40 (6 each for synthetic-idris and synthetic-noor, 2
  for Holliday); their holdout essays give only 10 or 11 passages. Gerould and Crothers passages are
  all new.
- **Small numbers.** 10 generator agents; per-author rates rest on 5 to 8 briefs and two agents each.
- **Process notes from the generators** (their logs are in `drafts/<arm>/_log-*.md`):
  - Several agents' shell globs printed other briefs (w*-05 to 08) or, in one lite agent's case, lines
    from another agent's finished drafts. All logged the slip and said they did not use the text.
  - The lite w4a agent found w4-01 to 04 already in `out/lite/` and overwrote them. The final files
    match that agent's own working drafts byte for byte (`work/lite-w4a/d01..04.md`), so no other
    arm's text is in the lite results.
  - The Idiolect w2b agent kept revising past write.md's two-revision limit to remove details it had
    invented; the w2a agent wrote placeholders with a comma instead of a colon because a colon inside
    a placeholder counted towards the colon metric. Both point at small fixes (placeholders excluded
    from measurement; the revision limit worded for invented content).
- **The spot-check is not done** (`spotcheck.md`, 5 judgments), so this run does not count yet.

## Process

- 40 briefs reused from the scratch folder, 40 generators (10 agents per arm, 4 briefs each, each with
  its own working folder), 40 judges (one packet each, 4 drafts), 24 recognition agents.
- Every draft was within 15% of its target length. Prompts are in `prompts/` and name no author.

## What this says about the design

Set out for the writer in the report; not decided here. The data points to: keep targets and the
check-and-revise loop; the lessons, phrases and forms are not earning their place in the writing kit
(the evaluation does not exercise edit lessons from a writer's own corrections, which is their main
purpose); and targets need to follow the mode of the piece, not the corpus average, for writers whose
texts vary.
