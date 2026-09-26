# Results, run 20260926T163528Z

Counted briefs exclude those whose passage a separate agent recognised with medium or high confidence.
The last column (all briefs, recognised included) is reported for information and decides nothing.

| Author | Briefs | Excluded (recognised) | vs plain | vs few-shot | Mean flags: plain / fewshot / idiolect / bare | All briefs: vs plain, vs few-shot |
| --- | --- | --- | --- | --- | --- | --- |
| katharine-fullerton-gerould | 4 | 0 | 4/4 (100%) | 4/4 (100%) | 3.25 / 1.5 / 0.5 / 0.5 | 4/4, 4/4 |
| robert-cortes-holliday | 10 | 0 | 10/10 (100%) | 4/10 (40%) | 2.6 / 2.5 / 1.2 / 1.2 | 10/10, 4/10 |
| samuel-mcchord-crothers | 10 | 3 | 4/7 (57%) | 2/7 (29%) | 3.43 / 3.43 / 0.14 / 0.14 | 7/10, 2/10 |
| synthetic-idris | 8 | 0 | 8/8 (100%) | 6/8 (75%) | 5.75 / 2.75 / 0.25 / 0.38 | 8/8, 6/8 |
| synthetic-noor | 8 | 0 | 8/8 (100%) | 6/8 (75%) | 7.25 / 2.38 / 1.5 / 1.0 | 8/8, 6/8 |

| Group | Counted | vs plain (bar 70%) | vs few-shot (bar 60%) | Pass this run |
| --- | --- | --- | --- | --- |
| real | 21 | 86% | 48% | no |
| synthetic | 16 | 100% | 75% | yes |

Pairwise win rates with 95% intervals from resampling generator agents (one agent writes several drafts, so the agent, not the brief, is the unit):

| Comparison | All | real | synthetic | By author |
| --- | --- | --- | --- | --- |
| idiolect vs plain | 92% (79%-100%, 11 agents) | 86% (67%-100%, 7 agents) | 100% (100%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 100%, samuel-mcchord-crothers 57%, synthetic-idris 100%, synthetic-noor 100% |
| idiolect vs fewshot | 60% (42%-74%, 11 agents) | 48% (22%-74%, 7 agents) | 75% (75%-75%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 40%, samuel-mcchord-crothers 29%, synthetic-idris 75%, synthetic-noor 75% |
| bare vs plain | 92% (81%-100%, 11 agents) | 86% (69%-100%, 7 agents) | 100% (100%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 90%, samuel-mcchord-crothers 71%, synthetic-idris 100%, synthetic-noor 100% |
| bare vs fewshot | 60% (34%-80%, 11 agents) | 38% (10%-67%, 7 agents) | 88% (75%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 20%, samuel-mcchord-crothers 29%, synthetic-idris 88%, synthetic-noor 88% |
| idiolect vs bare | 51% (35%-69%, 11 agents) | 67% (52%-84%, 7 agents) | 31% (12%-50%, 4 agents) | katharine-fullerton-gerould 50%, robert-cortes-holliday 70%, samuel-mcchord-crothers 71%, synthetic-idris 12%, synthetic-noor 50% |

First place by label: {'A': 7, 'B': 4, 'C': 12, 'D': 17}
