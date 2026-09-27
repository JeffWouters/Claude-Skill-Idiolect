"""langpack: list and check the language packs (spec §32). Read-only.

    python3 langpack.py list
    python3 langpack.py check [CODE]

A pack is references/lang/<code>/ with pack.yaml and the word lists of references/fingerprint.md.
`check` prints the problems found (none: status ok) and exits 1 when there are any.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure  # noqa: E402
from common import LANG_DIR, load_yaml_text  # noqa: E402

LISTS = ("hedges.txt", "openers.txt", "contractions.txt", "stopwords.txt")


def packs():
    return sorted(d.name for d in LANG_DIR.iterdir() if d.is_dir())


def check(code):
    d = LANG_DIR / code
    problems = []
    if not d.is_dir():
        return [f"{code}: no pack folder"]
    info = load_yaml_text((d / "pack.yaml").read_text(encoding="utf-8")) if (d / "pack.yaml").exists() else None
    if info is None:
        problems.append(f"{code}: no pack.yaml")
    else:
        if info.get("code") != code:
            problems.append(f"{code}: pack.yaml says code {info.get('code')!r}")
        for key in ("name", "version", "calibrated"):
            if key not in info:
                problems.append(f"{code}: pack.yaml has no {key}")
    for name in LISTS:
        f = d / name
        if not f.exists():
            continue
        seen = set()
        for n, raw in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if not raw or raw.startswith("#"):
                continue
            if raw != raw.strip():
                problems.append(f"{code}/{name} line {n}: leading or trailing spaces")
            if name != "contractions.txt" and raw != raw.lower():
                problems.append(f"{code}/{name} line {n}: not lower case")
            if raw in seen:
                problems.append(f"{code}/{name} line {n}: duplicate {raw!r}")
            seen.add(raw)
            if name == "contractions.txt":
                try:
                    re.compile(raw)
                except re.error as e:
                    problems.append(f"{code}/{name} line {n}: not a valid pattern ({e})")
    return problems


def listing():
    out = []
    for code in packs():
        info = measure.pack_info(code) or {}
        out.append({"code": code, "name": info.get("name"), "version": info.get("version"),
                    "calibrated": info.get("calibrated"), "metrics": len(measure.applicable(code)),
                    "lists": [n for n in LISTS if (LANG_DIR / code / n).exists()]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["list", "check"])
    ap.add_argument("code", nargs="?")
    a = ap.parse_args(argv)
    if a.action == "list":
        print(json.dumps({"packs": listing()}, indent=1, ensure_ascii=False))
        return 0
    problems = []
    for code in ([a.code] if a.code else packs()):
        problems += check(code)
    print(json.dumps({"status": "ok" if not problems else "problems", "problems": problems}, indent=1,
                     ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
