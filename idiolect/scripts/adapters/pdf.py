"""PDF adapter (spec §6.3): pdfminer.six layout analysis; text boxes are blocks."""
import collections
import re

from . import Extract

PAGE_NO = re.compile(r"^\s*(page\s*)?\d+(\s*(/|of)\s*\d+)?\s*$", re.I)


def _date(raw):
    # PDF date: D:YYYYMMDDHHmmSS...
    if isinstance(raw, bytes):
        raw = raw.decode("latin-1", "ignore")
    m = re.match(r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?", str(raw or ""))
    if not m:
        return None
    y, mo, d = m.group(1), m.group(2) or "01", m.group(3) or "01"
    return f"{y}-{mo}-{d}"


def extract(path):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextBox
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser

    date = None
    with open(path, "rb") as fh:
        try:
            doc = PDFDocument(PDFParser(fh))
            for info in doc.info:
                if "CreationDate" in info:
                    val = info["CreationDate"]
                    val = val.resolve() if hasattr(val, "resolve") else val
                    date = _date(val)
        except Exception:  # noqa: BLE001 - metadata is optional
            pass

    pages, flags = [], []
    for n, page in enumerate(extract_pages(str(path)), 1):
        boxes = []
        for el in page:
            if isinstance(el, LTTextBox):
                lines = [ln.get_text().strip() for ln in el]
                boxes.append([ln for ln in lines if ln])
        if not any(boxes):
            flags.append(f"page {n} has no text layer")
        pages.append(boxes)

    repeated = set()
    if len(pages) >= 3:
        counts = collections.Counter()
        for boxes in pages:
            counts.update({ln for box in boxes for ln in box})
        repeated = {ln for ln, c in counts.items() if c * 2 >= len(pages)}

    blocks = []
    for boxes in pages:
        for box in boxes:
            kept = [ln for ln in box if ln not in repeated and not PAGE_NO.match(ln)]
            text = ""
            for ln in kept:
                if text.endswith("-") and ln[:1].islower():
                    text = text[:-1] + ln
                else:
                    text = (text + " " + ln) if text else ln
            if text.strip():
                blocks.append(text.strip())
    return Extract(blocks=blocks, date=date, flags=flags)
