# A learn over the bridge (phase 6 exit, third part)

On 2026-09-26 a cloud session (this repository's container) ran a full `learn` on the writer's
computer through the device bridge's shell, following `idiolect/references/runtime.md` (shell route):

- **Engine:** the repository's `idiolect/` folder as synced on the computer; `check_env.py` there
  passed (Python 3.10.12, all dependencies).
- **Store and sources:** a new store and six synthetic-noor fixture essays in a scratch folder on the
  computer (`bridge-e2e/Store`, `bridge-e2e/Writing/sam`), so nothing of the writer's own was touched.
- **Script steps through the shell:** `learn.py init`, `start`, `answer`, `stage-texts`, `measure`,
  `contrast-sample`, `contrast-apply`, `lessons-sample`, `lessons-apply`, `vocab-apply`,
  `examples-sample`, `examples-apply`, `stage.py diff`, `decide`, `commit`, then `status`, `kit.py`
  and `check.py`.
- **Model steps:** the four neutral rewrites came from a fresh agent that saw only the paragraphs;
  lessons, vocabulary and examples were written in the session from the sample files the scripts left in
  the store's pending area, read through the shell. The rewrites and lesson files were written back
  through the same shell. No source file was copied to the cloud workspace.
- **Result:** 24 items approved and committed, one snapshot; slot `en.essay` (6 texts, 3,987 words,
  confidence medium), four lessons, three examples, one vocabulary entry. A held-out essay of the same
  author (`09-the-list-on-the-fridge.md`) passes `check` against the new profile (1 of 14 flagged).

The file-bridge route (`bridge.py`) is covered by `tests/test_bridge.py` only: this session's bridge
has a shell, which is the route the design now prefers.
