# Results, run 20260926T154434Z

Counted briefs exclude those whose passage a separate agent recognised with medium or high confidence.
The last column (all briefs, recognised included) is reported for information and decides nothing.

| Author | Briefs | Excluded (recognised) | vs plain | vs few-shot | Mean flags: plain / fewshot / idiolect / lite | All briefs: vs plain, vs few-shot |
| --- | --- | --- | --- | --- | --- | --- |
| katharine-fullerton-gerould | 8 | 1 | 7/7 (100%) | 3/7 (43%) | 2.71 / 1.29 / 0.0 / 2.71 | 8/8, 3/8 |
| robert-cortes-holliday | 8 | 3 | 5/5 (100%) | 3/5 (60%) | 3.6 / 4.2 / 1.2 / 3.8 | 8/8, 4/8 |
| samuel-mcchord-crothers | 8 | 1 | 7/7 (100%) | 5/7 (71%) | 3.29 / 2.86 / 0.43 / 4.29 | 8/8, 5/8 |
| synthetic-idris | 8 | 0 | 8/8 (100%) | 5/8 (62%) | 6.88 / 3.0 / 0.38 / 4.5 | 8/8, 5/8 |
| synthetic-noor | 8 | 0 | 8/8 (100%) | 6/8 (75%) | 7.0 / 2.5 / 1.0 / 3.62 | 8/8, 6/8 |

| Group | Counted | vs plain (bar 70%) | vs few-shot (bar 60%) | Pass this run |
| --- | --- | --- | --- | --- |
| real | 19 | 100% | 58% | no |
| synthetic | 16 | 100% | 69% | yes |

Pairwise win rates with 95% intervals from resampling generator agents (one agent writes several drafts, so the agent, not the brief, is the unit):

| Comparison | All | real | synthetic | By author |
| --- | --- | --- | --- | --- |
| idiolect vs plain | 100% (100%-100%, 10 agents) | 100% (100%-100%, 6 agents) | 100% (100%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 100%, samuel-mcchord-crothers 100%, synthetic-idris 100%, synthetic-noor 100% |
| idiolect vs fewshot | 63% (51%-72%, 10 agents) | 58% (41%-70%, 6 agents) | 69% (56%-75%, 4 agents) | katharine-fullerton-gerould 43%, robert-cortes-holliday 60%, samuel-mcchord-crothers 71%, synthetic-idris 62%, synthetic-noor 75% |
| lite vs plain | 100% (100%-100%, 10 agents) | 100% (100%-100%, 6 agents) | 100% (100%-100%, 4 agents) | katharine-fullerton-gerould 100%, robert-cortes-holliday 100%, samuel-mcchord-crothers 100%, synthetic-idris 100%, synthetic-noor 100% |
| lite vs fewshot | 51% (33%-69%, 10 agents) | 53% (35%-74%, 6 agents) | 50% (19%-75%, 4 agents) | katharine-fullerton-gerould 29%, robert-cortes-holliday 60%, samuel-mcchord-crothers 71%, synthetic-idris 25%, synthetic-noor 75% |
| idiolect vs lite | 69% (56%-79%, 10 agents) | 58% (41%-71%, 6 agents) | 81% (75%-94%, 4 agents) | katharine-fullerton-gerould 71%, robert-cortes-holliday 40%, samuel-mcchord-crothers 57%, synthetic-idris 88%, synthetic-noor 75% |

First place by label: {'A': 10, 'B': 7, 'C': 12, 'D': 11}
