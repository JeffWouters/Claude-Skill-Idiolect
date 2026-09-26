# Modes: forget, rollback, prune

The only modes that delete. Each builds a proposal; nothing changes until the writer approves the
diff (`stage.py diff`, `decide`, `commit`). Where the environment needs permission to delete, ask
for it at commit time and say why.

## forget

```
python3 scripts/maintain.py --store S forget --source <path or key> [--profile P] [--ownership own|assisted|exclude]
```

- Without `--ownership`: removes the text from `--profile` (or from every profile). When no profile
  owns it any more, its cached text is deleted; with no profile left it becomes `forgotten`, and
  later learns skip it.
- With `--ownership`: reclassifies it. `own` extracts and caches it again, also for a forgotten text,
  as long as the file still gives the same text.
- Affected slots are re-measured in the same proposal. Lessons are refreshed at the next `learn`;
  say so.

## rollback

```
python3 scripts/maintain.py --store S rollback --profile P [--to <snapshot name>]
```

Restores the profile's files from the snapshot (latest by default), removes files created after it,
and restores that profile's ownership records, statuses and holdout flags. Other profiles are never
touched. The commit takes a new snapshot first, so a rollback can itself be rolled back.

## prune

```
python3 scripts/maintain.py --store S prune --profile P [--keep 10]
```

Removes all but the newest `keep` snapshots. Pruning takes no snapshot of its own.
