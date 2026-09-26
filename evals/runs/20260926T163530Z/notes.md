# Runs 20260926T163528Z (run 5) and 20260926T163530Z (run 6): notes

The confirming runs after the writer's decision on run 4 (design: decision log). Both use the new
design: observed lessons are background in the kit, and targets blend the slot with the example
passages chosen for the brief. Every passage is fresh: no paragraph appeared in runs 1 to 4, and none
is shared between runs 5 and 6 (`evals/eval-protocol.md`, "Runs 5 and 6"). The four arms were plain,
few-shot, Idiolect (the new default kit) and bare (the same, with `kit.py --notes none`).

## Outcome

**The synthetic group meets the bar in both runs. The real-author group misses it in both.
Phase 3 is therefore not done under the protocol**, which needs both groups.

| Group | Run | Idiolect vs plain | Idiolect vs few-shot (bar 60%) | Pass |
| --- | --- | --- | --- | --- |
| synthetic | 5 | 16/16 | 12/16 (75%) | yes |
| synthetic | 6 | 16/16 | 11/16 (69%) | yes |
| real | 5 | 18/21 (86%) | 10/21 (48%) | no |
| real | 6 | 13/18 (72%) | 6/18 (33%) | no |

Pooled over both runs (`harness.py pool`): synthetic 23 of 32 against few-shot, one-sided p = 0.01, and
32 of 32 against plain, so the synthetic group **passes**. Real 16 of 39 against few-shot (p = 0.90),
31 of 39 against plain, so the real group **fails**.

By author, Idiolect against few-shot over both runs (counted briefs): Gerould 6 of 6, synthetic-idris
12 of 16, synthetic-noor 11 of 16, Holliday 8 of 20, Crothers 2 of 13.

**Idiolect against bare** (does the background still help?): 39 of 71 (55%, p = 0.24): real 23 of 39,
synthetic 16 of 32. Keeping only the usual habits as background neither clearly helps nor hurts.

## Why the real group fails here

The real passages in these runs come mostly from **other books** by the same authors (Holliday's
*Turns about Town*, 1921, and Crothers's *Humanly Speaking*, 1912). Those books are measurably plainer
than the books the profiles were learned from, and Idiolect holds drafts to the learned book:

| Author | Metric | Profile (learned book) | Held-out passages | Few-shot | Idiolect | Bare |
| --- | --- | --- | --- | --- | --- | --- |
| Crothers | sentences over 28 words | 17% | 7% | 7% | 18% | 20% |
| Crothers | semicolons per 1,000 words | 3.0 | 1.6 | 2.7 | 3.3 | 3.6 |
| Crothers | average sentence length | 19.9 | 16.4 | 16.0 | 17.7 | 19.0 |
| Holliday | semicolons per 1,000 words | 7.3 | 1.7 | 4.3 | 4.5 | 5.8 |
| Holliday | average sentence length | 18.2 | 16.7 | 14.2 | 16.9 | 18.0 |

The judges say the same thing in words: Idiolect's Crothers drafts are "long, balanced periodic
sentences, epigrams", "more polished and epigrammatic than the passage's homelier plainness"; the
few-shot drafts have "plain, short declarative sentences ... closest to the passage's easy, genial
movement". Few-shot drafts drift towards plainer default prose, and here that happens to match the
later book. The blended targets pulled Holliday's semicolons down from run 4 (7.3 to 4.5) but not far
enough for a book that uses 1.7.

Gerould, whose passages still come from the learned book, went 6 of 6. That fits the explanation, but
it is only six briefs.

This does not rescue the real-author result. **Across all six runs Idiolect has never met the
few-shot bar on real authors** (40%, 57%, 37%, 58%, 48%, 33%; run 1 counts the 10 real briefs not
recognised, runs 2 and 3 had no recognition check), with same-book passages (runs 1 to 4) or
other-book passages (runs 5 and 6). What runs 5 and 6 add is a reason that matters for real use: a
profile learned from one period of a writer's work pulls new drafts towards that period.

## Caveats

- **The synthetic held-out essays were written for these runs** from a style specification
  reconstructed from the fixture essays, by agents that saw only the specification. `check` reads them
  as the authors' own, but they may favour whichever arm writes most like a written description of
  the voice. The synthetic pass is real, but softer than it looks.
- **Recognition**: 8 of 47 real-author passages were recognised at medium confidence and left out.
  The recognition agents named the right author for 41 of 47, mostly at low confidence, so the
  model's prior knowledge of the real authors is present in every real brief.
- **Gerould** had only 7 fresh passages left (4 and 3); Holliday and Crothers had 10 per run, so the real
  group leans on those two authors.
- **Small numbers per author**; 11 generator agents per arm per run; per-author rates are rough.
- **Process notes** (generator logs in `drafts/<arm>/_log-*.md`): some shell globs printed other
  briefs, which were logged and not used. One brief writer turned `/dev/null` in the workspace into a
  file while listing briefs; it was restored, and the lost brief was rewritten before any generator ran.
  29 briefs over 60 words and 3 with a wrong Length line were fixed before generation (the brief
  writers shortened their own briefs; the Length lines were corrected mechanically).
- **The spot-checks are not done** (`spotcheck.md` in both run folders).

## What this says about the design

Set out for the writer in the report. In short, the machinery (targets and the check-and-revise loop)
reliably helps against few-shot for regular, consistent voices, and does not for real essayists whose
style varies across books and years. The protocol's own rule ("missing the few-shot bar means the
machinery adds nothing, and the design changes") applies to the real group.
