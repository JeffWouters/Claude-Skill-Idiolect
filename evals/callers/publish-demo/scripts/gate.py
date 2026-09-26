#!/usr/bin/env python3
"""The publish gate of the demonstration skill (spec §25): run Idiolect's check non-interactively and
publish only on pass or low_confidence. Prints JSON {"action": published|blocked|stopped, ...}."""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

PUBLISH_ON = ("pass", "low_confidence")
STOP_ON = ("no_store", "no_slot", "needs_input", "error")


def gate(idiolect, store, profile, type_, file, dest):
    cmd = [sys.executable, str(pathlib.Path(idiolect) / "scripts" / "check.py"), "--file", str(file), "--json",
           "--type", type_]
    if store:
        cmd += ["--store", str(store)]
    if profile:
        cmd += ["--profile", profile]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        report = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"action": "stopped", "status": "error", "message": (r.stderr or r.stdout).strip()[-500:]}
    status = report.get("status")
    if status in PUBLISH_ON:
        d = pathlib.Path(dest)
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(file, d / pathlib.Path(file).name)
        return {"action": "published", "status": status, "to": str(d / pathlib.Path(file).name),
                "flagged": report.get("flagged"), "slot": report.get("slot")}
    if status in STOP_ON:
        return {"action": "stopped", "status": status, "message": report.get("message", "")}
    flagged = [f"{m['name']} {m['flag']}" for m in report.get("metrics", []) if m.get("flag") != "ok"]
    return {"action": "blocked", "status": status, "flagged": flagged,
            "bunched": report.get("bunched", []), "slot": report.get("slot")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--idiolect", required=True)
    ap.add_argument("--store")
    ap.add_argument("--profile")
    ap.add_argument("--type", default="essay")
    ap.add_argument("--file", required=True)
    ap.add_argument("--dest", default="published")
    a = ap.parse_args()
    out = gate(a.idiolect, a.store, a.profile, a.type, a.file, a.dest)
    print(json.dumps(out, indent=1))
    sys.exit(0 if out["action"] == "published" else 1)
