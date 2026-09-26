"""Redaction (spec §15). The script pass replaces patterns; the model pass supplies names of people
and organisations other than the writer, which this script then replaces consistently.

    python3 redact.py --file TEXT [--names names.yaml]     prints the redacted text and the replacements
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

VERSION = "1.0"

PATTERNS = [
    ("[email]", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("[iban]", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")),
    ("[url]", re.compile(r"\bhttps?://\S*?/(?:users?|u|profile|people|~)[/\w.%-]*", re.I)),
    ("[phone]", re.compile(r"(?<![\w/])(?:\+|00)\d{1,3}[\s.-]?(?:\(0\)[\s.-]?)?\d{1,4}(?:[\s.-]?\d{2,4}){2,4}\b"
                           r"|(?<![\w/])0\d{1,3}[\s.-]?\d{3,4}[\s.-]?\d{3,4}\b")),
    ("[postcode]", re.compile(r"\b\d{4}\s?[A-Z]{2}\b(?=[\s,.]|$)|\b[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}\b")),
]


def redact(text, names=None):
    """Returns (redacted text, replacements [{found, placeholder}])."""
    repl = []
    for placeholder, rx in PATTERNS:
        def sub(m, placeholder=placeholder):
            repl.append({"found": m.group(0), "placeholder": placeholder})
            return placeholder
        text = rx.sub(sub, text)
    for n in sorted(names or [], key=lambda x: -len(x["name"])):
        name, ph = n["name"], n.get("placeholder", "[person]")
        rx = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
        if rx.search(text):
            repl.append({"found": name, "placeholder": ph})
            text = rx.sub(ph, text)
    return text, repl


def record(replacements):
    return {"redacted": True, "version": VERSION, "reviewed": False}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True)
    ap.add_argument("--names")
    a = ap.parse_args(argv)
    names = None
    if a.names:
        from common import load_yaml_text
        names = load_yaml_text(pathlib.Path(a.names).read_text(encoding="utf-8"))
    text, repl = redact(pathlib.Path(a.file).read_text(encoding="utf-8"), names)
    print(json.dumps({"text": text, "replacements": repl, "version": VERSION}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
