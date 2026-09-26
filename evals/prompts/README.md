# Generator prompt templates

`harness.py prepare` fills these in for each generator agent ({SC} scratch folder, {W} anonymous
author, {G} agent id, {FILES} its briefs, {ARM} the arm) and writes them to `<scratch>/prompts/`, so
no prompt names an author or points into the repository. Each agent is started with: "Read the file
<scratch>/prompts/gen-<arm>-<agent>.txt and follow its instructions exactly. It is your whole task."
