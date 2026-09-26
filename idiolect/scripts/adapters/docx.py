"""Word adapter (spec §6.2): read word/document.xml directly so tracked insertions are kept and
deletions dropped. Standard library only."""
import re
import xml.etree.ElementTree as ET
import zipfile

from . import Extract

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DC = "{http://purl.org/dc/terms/}"
SKIP = {W + "del", W + "moveFrom", W + "commentReference", W + "footnoteReference"}


def _text(el, out):
    for child in el:
        if child.tag in SKIP:
            continue
        if child.tag == W + "t":
            out.append(child.text or "")
        elif child.tag == W + "tab":
            out.append(" ")
        elif child.tag in (W + "br", W + "cr"):
            out.append("\n")
        else:
            _text(child, out)


def extract(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        created = None
        if "docProps/core.xml" in z.namelist():
            core = ET.fromstring(z.read("docProps/core.xml"))
            el = core.find(DC + "created")
            created = el.text.strip() if el is not None and el.text else None
    blocks = []
    for p in root.iter(W + "p"):
        out = []
        _text(p, out)
        b = re.sub(r"\s*\n\s*", " ", "".join(out)).strip()
        if b:
            blocks.append(b)
    return Extract(blocks=blocks, date=created)
