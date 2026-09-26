# Learning from web pages and connector mail

Texts with no file on the writer's computer: pages of their blog or site, and mail from their sent
items through a Microsoft 365 connector (spec §23). They are added to a learn run with no inventory,
then learned exactly like files, with the same diff and approval. Store-writing.

## 1. Start

```
python3 scripts/connector.py --store S start --profile P --lang L --type T [--facet channel=x]
```

One slot per run: pages of one kind (`type=post`), or mail (`type=email`).

## 2a. Web pages

Fetch raw, never through a summarising web tool (those rewrite the text):

```
python3 scripts/web.py fetch --url <page, sitemap or feed> [--max 50] --out <scratch folder>
```

It keeps each page's main text (no menus, headers, footers or sidebars) and writes an `index.json`
with the URL, date and words. Pages under 150 words are skipped. If the fetch is refused because the
session has no network access to the site, say so and offer to learn from a saved copy instead.

Show the writer the list of pages and ask which are theirs alone (`own`), which they wrote with help
or edited from someone else's draft (`assisted`), and which are not theirs (`exclude`). Never assume
`own`: a site holds guest posts and quotes. Then per page:

```
python3 scripts/connector.py --store S add --file <NNN.txt> --origin web --ownership own --date <date> --note <url>
```

## 2b. Microsoft 365 mail

Only when the Microsoft 365 connector is available and the writer asks for it.

- Search the writer's **sent** items only, at most 10 messages per call; mail they received is not
  their voice. Prefer longer messages: under 150 words is skipped.
- Show subjects and dates and ask which to learn from and with which ownership (a mail drafted by an
  assistant or a template is `assisted` at most).
- Read each chosen message's body, list the names of people and organisations other than the writer's
  (`- {name: ..., placeholder: "[person]"}`), and give them once for the run:
  `python3 scripts/learn.py --store S mail-names --file names.yaml`.
- Save each body to a file and add it with quotes and the signature removed:

```
python3 scripts/connector.py --store S add --file <body.txt> --origin mail --ownership own --date <date> --note "<subject>" --strip
```

Mail is kept in the corpus redacted. Say that the store keeps the text, not the message or its
recipients.

## 3. Learn and approve

Continue with `references/modes/learn.md` from **measurement** (`learn.py measure`): contrast,
lessons, vocabulary, examples, the diff and the commit.
