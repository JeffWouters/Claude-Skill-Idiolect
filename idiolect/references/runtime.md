# Runtime

## Local route (this version)

Scripts run next to the files: Claude Code, or any session with a shell on the machine that holds
the sources and the store. Run them from the skill folder (`python3 scripts/<name>.py`); every script
prints JSON or a short summary and never needs network access.

- **Dependencies:** Python 3.10+, `PyYAML`, `jsonschema`, `markdown-it-py`, `pdfminer.six`,
  `lingua-language-detector`. `scripts/check_env.py` lists what is missing and the install line.
- **Paths:** `sources_root` in `idiolect.yaml` is relative to the store, and every path inside the
  store is relative to `sources_root`, with `/` separators. The same store works on Windows and
  Linux.
- **Lock:** store-writing modes take `.state/lock`; read-only modes and dry runs never do. A lock
  whose heartbeat is an hour old is taken over.
- **No remembered state:** the store is found per session. For a permanent default, suggest one
  line the writer can add to their own project instructions; never write it yourself.

## Bridged route

A cloud session that reaches the writer's computer through a bridge (spec §26). The store and the
sources stay on the computer.

### With a shell on the computer (the usual case)

1. Find a copy of this skill on the computer: an installed skill folder the shell can see, or copy
   this skill folder into `<store>/.state/engine/` (the store's own run state; replace it when this
   skill's version differs). Never copy it into a source folder.
2. Run `python3 <engine>/scripts/check_env.py` through the shell. If something is missing, show the
   install line and stop, or use the file route below.
3. Run every script through the shell exactly as on the local route, with the store and targets as
   the computer names them. Nothing is copied; source text stays on the computer. Model steps
   (contrast rewrites, lessons, examples) read the samples the scripts write into the store's pending
   area through the same shell.
4. The writer approves the diff as usual. Deleting (`forget`, `rollback`, `prune`) may need the
   writer's delete permission on that folder; ask for it at commit time and say why.

### Without a usable shell (file bridge)

Say first that source text will be copied into the cloud workspace for this session. Then:

1. Copy the store (it is small) into the workspace, keeping its path relative to the sources root.
2. List the target recursively on the computer, save it as a listing (`bridge.py` docstring), and run
   `python3 scripts/bridge.py plan --store <mirror> --listing L`: copy each batch of at most 50 files
   into the mirror, keeping relative paths.
3. `bridge.py snapshot --store <mirror> --out before.json`, then run the mode on the mirror as on the
   local route, approval included.
4. `bridge.py changed --store <mirror> --before before.json`: write each batch back to the computer
   (at most 50 files per call); deletions need the writer's permission. Only after everything is
   back: `bridge.py record --store <mirror> --listing L`, and write `.state/bridge.json` back too.
5. If a write-back fails halfway, say which files are back and which are not, and do not start another
   run on that store until the rest is written.
