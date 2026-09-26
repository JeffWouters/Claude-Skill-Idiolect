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

## Bridged route (later)

A cloud session linked to the writer's computer through a file bridge: inventory and hashing on the
computer, extraction and measurement in the cloud workspace, files copied at most 50 per call, and a
notice to the writer before any source text leaves their machine. Not available in this version.
