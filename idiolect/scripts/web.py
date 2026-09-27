"""web: fetch pages raw over HTTP and keep their main text (spec §23.2). Never through a summarising
tool. The texts are then added to a connector run (connector.py add --origin web).

    python3 web.py fetch --url URL [--max 50] --out DIR

A sitemap gives its pages, an RSS or Atom feed its items (with dates), anything else is one page.
Writes DIR/NNN.txt and DIR/index.json: [{file, url, date, words}]; pages under 150 words are listed
with "skipped".
"""
import argparse
import html
import json
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import StoreError, count_words  # noqa: E402

TIMEOUT = 20
MIN_WORDS = 150
AGENT = "Idiolect/1 (+learning a writer's own pages)"
DROP = ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "template", "title",
        "pre")        # code blocks are not the writer's prose (the Markdown adapter drops fenced code too)
BLOCK = r"p|div|section|article|main|li|ul|ol|h[1-6]|blockquote|pre|tr|table|br|hr|figure|figcaption|dd|dt"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/xml,*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:     # noqa: S310 - the writer's own URL
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def feed_or_sitemap(text):
    """('sitemap', [(url, None)]), ('index', [urls]), ('feed', [(url, date)]) or (None, [])."""
    head = text.lstrip()[:500].lower()
    if not head.startswith("<?xml") and not re.match(r"<(rss|feed|urlset|sitemapindex)\b", head):
        return None, []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return None, []
    kind = _local(root.tag)
    if kind == "urlset":
        return "sitemap", [(e.text.strip(), None) for e in root.iter() if _local(e.tag) == "loc" and e.text]
    if kind == "sitemapindex":
        return "index", [e.text.strip() for e in root.iter() if _local(e.tag) == "loc" and e.text]
    items = []
    if kind == "rss":
        for it in root.iter("item"):
            link = (it.findtext("link") or "").strip()
            items.append((link, _date(it.findtext("pubDate"))))
    elif kind == "feed":
        for en in root:
            if _local(en.tag) != "entry":
                continue
            link = next((l.get("href") for l in en if _local(l.tag) == "link" and l.get("rel", "alternate") == "alternate"), None)
            when = next((c.text for c in en if _local(c.tag) in ("published", "updated")), None)
            items.append(((link or "").strip(), _date(when)))
    return ("feed", [i for i in items if i[0]]) if kind in ("rss", "feed") else (None, [])


def _date(value):
    if not value:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return "-".join(m.groups())
    try:
        import email.utils
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return None


def page_date(doc):
    m = re.search(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', doc, re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time', doc, re.I) or \
        re.search(r'<time[^>]+datetime=["\']([^"\']+)', doc, re.I)
    return _date(m.group(1)) if m else None


def main_text(doc):
    """Paragraphs of the page's main text (spec §23.2)."""
    doc = re.sub(r"(?is)<!--.*?-->", " ", doc)
    for tag in DROP:
        doc = re.sub(rf"(?is)<{tag}\b[^>]*>.*?</{tag}\s*>", " ", doc)
    for tag in ("article", "main", "body"):
        m = re.search(rf"(?is)<{tag}\b[^>]*>(.*)</{tag}\s*>", doc)
        if m:
            doc = m.group(1)
            break
    doc = re.sub(rf"(?is)</?(?:{BLOCK})\b[^>]*>", "\n\n", doc)
    doc = re.sub(r"(?s)<[^>]+>", "", doc)
    doc = html.unescape(doc)
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", doc)]
    return [p for p in paras if p]


def fetch(url, max_pages=50, out=None):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    first = get(url)
    kind, items = feed_or_sitemap(first)
    if kind == "index":
        pages = []
        for sm in items:
            k2, it2 = feed_or_sitemap(get(sm))
            pages += it2
            if len(pages) >= max_pages:
                break
        items = pages
    pages = items[:max_pages] if kind else [(url, None)]
    index = []
    for n, (u, when) in enumerate(pages, 1):
        try:
            doc = first if not kind else get(u)
        except OSError as e:
            index.append({"url": u, "skipped": f"could not fetch: {e}"})
            continue
        paras = main_text(doc)
        text = "\n\n".join(paras)
        words = count_words(text)
        row = {"url": u, "date": when or page_date(doc), "words": words}
        if words < MIN_WORDS:
            row["skipped"] = f"only {words} words"
        else:
            f = out / f"{n:03d}.txt"
            f.write_text(text + "\n", encoding="utf-8")
            row["file"] = str(f)
        index.append(row)
    (out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"kind": kind or "page", "pages": len(pages), "kept": sum(1 for r in index if "file" in r),
            "index": str(out / "index.json")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["fetch"])
    ap.add_argument("--url", required=True)
    ap.add_argument("--max", type=int, default=50)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        out = fetch(a.url, a.max, a.out)
    except (StoreError, OSError, ValueError) as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=1))
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
