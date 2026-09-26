"""Start-up check: names anything the engine needs that is missing.

    python3 check_env.py            exit 0 when everything is present
"""
import importlib
import json
import sys

NEEDED = [
    ("yaml", "PyYAML", "store files"),
    ("jsonschema", "jsonschema>=4.18", "validating store files"),
    ("referencing", "referencing", "validating store files"),
    ("markdown_it", "markdown-it-py", "Markdown sources"),
    ("pdfminer", "pdfminer.six", "PDF sources"),
    ("lingua", "lingua-language-detector", "language identification"),
]


def check():
    missing = []
    if sys.version_info < (3, 10):
        missing.append({"package": "Python 3.10 or newer", "for": "everything",
                        "found": sys.version.split()[0]})
    for mod, pkg, why in NEEDED:
        try:
            m = importlib.import_module(mod)
            if mod == "jsonschema" and not hasattr(m, "Draft202012Validator"):
                missing.append({"package": pkg, "for": why + " (installed version is too old)",
                                "found": getattr(m, "__version__", "?")})
        except ImportError:
            missing.append({"package": pkg, "for": why})
    return missing


def main():
    missing = check()
    out = {"ok": not missing, "missing": missing}
    if missing:
        pkgs = " ".join(f'"{m["package"]}"' for m in missing if not m["package"].startswith("Python"))
        if pkgs:
            out["install"] = f"python3 -m pip install --upgrade {pkgs}"
    print(json.dumps(out, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
