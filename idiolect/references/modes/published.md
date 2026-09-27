# Mode: published

Learn from what the writer publishes (spec §33). Idiolect keeps the drafts it writes; when the writer
publishes an edited version, a scan finds it, pairs it with its draft and queues the pair for
`learn-edit`. The scan learns nothing by itself, so it can run unattended. Run scripts from the skill
folder.

## 1. Set it up (once)

Ask where the writer publishes: a folder (their blog's source, a "Published" folder), a folder in their
Obsidian vault, or a feed (the blog's RSS or Atom feed, or a sitemap). Each source belongs to one
profile, with a type when the source holds one kind of text.

```
python3 scripts/published.py --store S keep-drafts on
python3 scripts/published.py --store S add-source --folder ~/Vault/Published --profile P --type post
python3 scripts/published.py --store S add-source --feed https://example.com/feed.xml --profile P --type essay
python3 scripts/published.py --store S show
```

A folder is an absolute path or starts with `~`, and is never inside the store. Hidden folders (such as
`.obsidian`) are skipped. `remove-source --id pub-NNN` removes one; `keep-drafts off` stops keeping drafts.

## 2. Keeping drafts

With `keep_drafts` on, `write` and `rewrite` keep every draft they return (`write.md`, step 6). Kept
drafts older than 90 days that were never published expire.

## 3. Scan

```
python3 scripts/published.py --store S scan
```

Relay the result: how many published texts matched a kept draft (queued), which texts matched none
(`unmatched`: candidates for `learn`, as their own texts), what was skipped and why, and which drafts
expired. The first scan reads every file in a folder; later scans read only what changed since.

## 4. Process the queue

```
python3 scripts/published.py --store S queue
```

For each waiting item, run `learn-edit` (`learn-edit.md`) with the item's kept draft and published
version, both paths relative to the store:

```
python3 scripts/learn_edit.py --store S start --draft S/<draft_file> --final S/<final_file> --profile P --type T
```

Then the kinds, the diff and the writer's approval, as always. After the commit, or when the writer
says to skip the item, close it:

```
python3 scripts/published.py --store S done --id q-001 [--skipped]
```

## Scheduled

The writer can have the scan run by itself, for example weekly. Create it as a scheduled task that
needs the writer's computer (the store and the folders are there), with this prompt, filled in:

> Use the Idiolect skill. Run `python3 scripts/published.py --store <store> scan` from the skill folder.
> Report in a few lines how many published texts were queued for learn-edit, which texts matched no
> draft, and which drafts expired. Do not run learn-edit and do not approve anything: end by telling
> the writer to say "process my Idiolect edit queue" when they have time. If the scan reports that
> another run holds the lock, say so and stop.

## interactive=false

Never ask. `scan`, `queue` and `show` return JSON; queued items wait for an interactive `learn-edit`.
