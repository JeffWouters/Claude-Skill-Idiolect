---
name: publish-demo
description: Demonstration publishing skill for the Idiolect phase 6 exit test. Use when the user asks to publish a draft with publish-demo. Publishes a Markdown draft into a published/ folder only after Idiolect's check passes for the writer's profile.
---

# publish-demo

A stand-in for a real publishing skill (a newsletter or blog publisher). It shows how a caller uses
Idiolect: it never asks Idiolect questions and never writes to its store.

1. Find the draft file, the Idiolect store (`store=`, or discovery as Idiolect does it), the profile
   and the type. If the user did not say the type, use `essay`.
2. Call Idiolect's `check` with `interactive=false` and read its report. Run the gate, which does
   exactly that and publishes only on `pass` or `low_confidence`:

   ```
   python3 scripts/gate.py --idiolect <path to the idiolect skill folder> --store <store> --profile <profile> --type <type> --file <draft> --dest published
   ```

3. Relay the gate's result in one or two lines:
   - `published`: say where the file went, and the check's status (say "low confidence" when it was).
   - `blocked`: do not publish, do not edit the draft to force a pass. Give Idiolect's status and the
     flagged metrics or message, and suggest the writer revise the draft or ask Idiolect to rewrite it.
   - `stopped` (`no_store`, `no_slot`, `needs_input`, `error`): say what Idiolect needs, in its own
     words, and stop.
