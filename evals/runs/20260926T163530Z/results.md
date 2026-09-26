# Results, run 20260926T163530Z

Counted briefs exclude those whose passage a separate agent recognised with medium or high confidence.
The last column (all briefs, recognised included) is reported for information and decides nothing.

| Author | Briefs | Excluded (recognised) | vs plain | vs few-shot | Mean flags: plain / fewshot / idiolect / bare | All briefs: vs plain, vs few-shot |
| --- | --- | --- | --- | --- | --- | --- |
| katharine-fullerton-gerould | 3 | 1 | 2/2 (100%) | 2/2 (100%) | 2.5 / 1.5 / 0.0 / 0.5 | 3/3, 3/3 |
| robert-cortes-holliday | 10 | 0 | 6/10 (60%) | 4/10 (40%) | 3.1 / 3.5 / 1.1 / 1.3 | 6/10, 4/10 |
| samuel-mcchord-crothers | 10 | 4 | 5/6 (83%) | 0/6 (0%) | 2.33 / 2.0 / 0.83 / 0.0 | 9/10, 1/10 |
| synthetic-idris | 8 | 0 | 8/8 (100%) | 6/8 (75%) | 7.25 / 2.0 / 0.12 / 0.12 | 8/8, 6/8 |
| synthetic-noor | 8 | 0 | 8/8 (100%) | 5/8 (62%) | 7.75 / 1.75 / 1.12 / 1.0 | 8/8, 5/8 |

| Group | Counted | vs plain (bar 70%) | vs few-shot (bar 60%) | Pass this run |
| --- | --- | --- | --- | --- |
| real | 18 | 72% | 33% | no |
| synthetic | 16 | 100% | 69% | yes |

Pairwise win rates with 95% intervals from resampling generator agents (one agent writes several drafts, so the agent, not the brief, is the unit):

| Comparison | All | real | synthetic | By author |
| --- | --- | --- | --- | --- |
| idiolect vs plain | 85% (59%-100%, 11 agents) | 72% (35%-100%, 7 agents) | 100% (100%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 60%, samuel-mcchord-crothers 83%, synthetic-idris 100%, synthetic-noor 100% |
| idiolect vs fewshot | 50% (28%-71%, 11 agents) | 33% (9%-67%, 7 agents) | 69% (50%-88%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 40%, samuel-mcchord-crothers 0%, synthetic-idris 75%, synthetic-noor 62% |
| bare vs plain | 88% (69%-100%, 11 agents) | 78% (50%-100%, 7 agents) | 100% (100%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 70%, samuel-mcchord-crothers 83%, synthetic-idris 100%, synthetic-noor 100% |
| bare vs fewshot | 38% (20%-56%, 11 agents) | 28% (5%-56%, 7 agents) | 50% (31%-69%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 30%, samuel-mcchord-crothers 0%, synthetic-idris 62%, synthetic-noor 38% |
| idiolect vs bare | 59% (43%-75%, 11 agents) | 50% (31%-73%, 7 agents) | 69% (50%-88%, 4 agents) | katharine-fullerton-gerould 50%, robert-cortes-holliday 50%, samuel-mcchord-crothers 50%, synthetic-idris 50%, synthetic-noor 88% |

First place by label: {'A': 13, 'B': 9, 'C': 8, 'D': 9}
