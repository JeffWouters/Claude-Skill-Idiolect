#!/usr/bin/env python3
"""Build idiolect.skill (a zip of the idiolect/ folder) for delivery. Never installs anything.

    python3 tools/build_package.py [--out DIR]
"""
import argparse
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "idiolect"
SKIP = {"__pycache__", ".pytest_cache"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT))
    a = ap.parse_args()
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    desc = re.search(r"^description: (.*)$", text, re.M).group(1)
    assert len(desc) < 1024 and "<" not in desc and ">" not in desc, "description breaks the frontmatter rules"
    out = pathlib.Path(a.out) / "idiolect.skill"
    files = sorted(p for p in SKILL.rglob("*") if p.is_file() and not (set(p.parts) & SKIP)
                   and not p.name.endswith((".pyc", ".tmp")))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, pathlib.Path("idiolect") / f.relative_to(SKILL))
    print(f"{out} ({len(files)} files)")


if __name__ == "__main__":
    main()
