"""Markdown adapter (spec §6.1): markdown-it-py, CommonMark plus tables, Obsidian links and callouts."""
import re

from markdown_it import MarkdownIt

from . import Extract

FRONT = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
EMBED = re.compile(r"!\[\[[^\]]*\]\]")
WIKI = re.compile(r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
TAG = re.compile(r"(?<![\w&/#])#[^\W\d_][\w/-]*")
FOOTREF = re.compile(r"\[\^[^\]]+\]")
FOOTDEF = re.compile(r"^\[\^[^\]]+\]:")
NUMERIC = re.compile(r"^[\s\d.,%€$£+\-]*\d[\s\d.,%€$£+\-]*$")
CALLOUT = re.compile(r"^\[![^\]]+\][+-]?")

_md = MarkdownIt("commonmark", {"html": True}).enable("table")


def _inline_text(tok):
    out = []
    for c in tok.children or []:
        if c.type == "text":
            out.append(c.content)
        elif c.type == "code_inline":
            if len(c.content) <= 40:
                out.append(c.content)
        elif c.type in ("softbreak", "hardbreak"):
            out.append("\n")
        # image, html_inline and markup tokens contribute nothing
    return "".join(out)


def _clean_inline(text):
    text = EMBED.sub("", text)
    text = WIKI.sub(lambda m: (m.group(2) if m.group(2) is not None else m.group(1)), text)
    text = FOOTREF.sub("", text)
    text = TAG.sub("", text)
    return text


def _block(text):
    lines = [ln.strip() for ln in text.split("\n")]
    return " ".join(ln for ln in lines if ln).strip()


def split_frontmatter(raw):
    m = FRONT.match(raw)
    if not m:
        return {}, raw
    from common import load_yaml_text  # scripts dir is on sys.path
    try:
        meta = load_yaml_text(m.group(1)) or {}
    except Exception:  # noqa: BLE001 - broken frontmatter is ignored, not fatal
        meta = {}
    return (meta if isinstance(meta, dict) else {}), raw[m.end():]


def extract(path):
    raw = path.read_text(encoding="utf-8-sig")
    meta, body = split_frontmatter(raw)
    tokens = _md.parse(body)
    blocks = []
    quote_depth = 0
    callout = False          # inside a top-level callout blockquote
    callout_title_pending = False
    table = None             # collecting rows: list of (is_header, [cells])
    row = None
    for i, t in enumerate(tokens):
        if t.type == "blockquote_open":
            quote_depth += 1
            if quote_depth == 1:
                nxt = next((x for x in tokens[i + 1:] if x.type == "inline"), None)
                callout = bool(nxt and CALLOUT.match(nxt.content))
                callout_title_pending = callout
            continue
        if t.type == "blockquote_close":
            quote_depth -= 1
            if quote_depth == 0:
                callout = False
            continue
        if quote_depth and not callout:
            continue
        if t.type == "table_open":
            table = []
            continue
        if t.type == "tr_open":
            row = []
            continue
        if t.type == "tr_close" and table is not None:
            table.append(row)
            row = None
            continue
        if t.type == "table_close":
            body_cells = [c for r in table[1:] for c in r if c.strip()]
            numeric = sum(1 for c in body_cells if NUMERIC.match(c))
            if not body_cells or numeric * 2 <= len(body_cells):
                for r in table:
                    b = _block(" ".join(c for c in r if c.strip()))
                    if b:
                        blocks.append(b)
            table = None
            continue
        if t.type != "inline":
            continue
        text = _clean_inline(_inline_text(t))
        if row is not None:
            row.append(_block(text))
            continue
        if callout_title_pending:
            callout_title_pending = False
            first, _, rest = text.partition("\n")
            text = rest
        if FOOTDEF.match(t.content):
            continue
        b = _block(text)
        if b:
            blocks.append(b)
    date = meta.get("date")
    return Extract(blocks=blocks, date=str(date) if date is not None else None,
                   meta={k: meta[k] for k in ("lang", "type", "tags") if k in meta})
