# Generator prompt templates

`harness.py prepare` fills these in for each generator agent ({SC} scratch folder, {W} anonymous
author, {G} agent id, {FILES} its briefs, {ARM} the arm) and writes them to `<scratch>/prompts/`, so
no prompt names an author or points into the repository. Each agent is started with: "Read the file
<scratch>/prompts/gen-<arm>-<agent>.txt and follow its instructions exactly. It is your whole task."

`gen-lite.txt` is run 4's lite arm (`evals/ablation/write-lite.md`); `gen-bare.txt` is the bare arm of runs 5
and 6 (`evals/ablation/write-bare.md`).

## Recognition and sensitivity (runs 7 on)

- `recognition.txt`: the forced-choice recognition check. `harness.py recognition` fills it in per
  passage and per positive control ({PASSAGE}, {CANDIDATES}: ten writers from
  `evals/recognition-candidates.json`, {OUT}) under shuffled ids r01.., so an agent cannot tell a
  control from a passage. `harness.py screen` uses it for screening new authors.
- `sens-blind.txt`, `sens-named.txt`: the sensitivity test. The same packet judged again, once blind
  and once told the author ({NAME}, {ABOUT}).

Each agent is started with: "Read the file <scratch>/<folder>/<id>.txt and follow its instructions
exactly. It is your whole task." Run these agents with memory off (eval-protocol.md, "Context").
