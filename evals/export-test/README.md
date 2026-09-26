# Export in another tool (phase 6 exit, second part)

Does a prompt from `export.py` carry the voice outside Idiolect? On 2026-09-26:

1. `export.py --store evals/store --profile synthetic-noor --type essay` wrote `synthetic-noor.export.md`.
2. `claude -p` (Claude Code's print mode: no skill, no store, a scratch folder) got that file followed by
   one brief: "Write an essay of about 350 words about repainting a garden bench after a wet winter:
   sanding it, choosing the paint, the second coat." → `export-draft.md`.
3. The same brief alone → `plain-draft.md`.
4. `check.py` against the profile: the export draft **passes** (3 of 14 metrics flagged, fails at 4);
   the plain draft **fails** (7 of 14). Reports in `*.check.json`.

One draft each is an illustration, not an evaluation: the blind judging of phases 3 and 4 is what says
whether a voice carries. It shows the prompt is self-contained and usable in a tool that has never seen
the store.
