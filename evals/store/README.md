# Idiolect store

This folder holds everything Idiolect has learned about one or more voices. It is yours: plain
YAML, JSON and Markdown files you can read, edit and version.

- `idiolect.yaml`: settings (where your texts are, facets, text types).
- `sources.yaml`: which folders and tags are learned from, and whose they are.
- `corpus/`: cleaned copies of your own texts, so learning can be repeated without the originals.
- `profiles/<name>/`: one voice each: slot pages with lessons, fingerprints, rulings, vocabulary,
  examples, rejections, a changelog and snapshots.
- `.state/`: the lock and anything waiting for your approval.

Nothing gets into this folder without your approval, except this README, the settings file and
the lock. Every approved change can be rolled back.
