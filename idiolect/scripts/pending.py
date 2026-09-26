"""Pending area (spec §9) and batch progress (design: Runtime).

    python3 pending.py --store S status     what is waiting, and which choices to offer
    python3 pending.py --store S discard    clear a pending area that has no commit journal

Staging, approval and the commit journal are completed in phase 2; this module already defines the
leftover rules (§9.6) so every store-writing run can check them first.
"""
import argparse
import json
import os
import shutil
import sys

from common import StoreError, iso, read_store_file, run_id, utcnow, write_json


def _dir(store_root):
    return os.path.join(store_root, ".state", "pending")


def status(store_root):
    plan_path = os.path.join(_dir(store_root), "plan.json")
    if not os.path.exists(plan_path):
        if os.path.isdir(_dir(store_root)) and os.listdir(_dir(store_root)):
            return {"pending": True, "plan": None, "choices": ["discard"],
                    "message": "pending folder without a plan (interrupted staging)"}
        return {"pending": False, "choices": []}
    plan = read_store_file(plan_path, "pending")
    items = plan["items"]
    summary = {d: sum(1 for i in items if i["decision"] == d) for d in ("pending", "approved", "rejected")}
    if "commit" in plan:
        todo = [s for s in plan["commit"]["steps"] if s["state"] == "todo"]
        return {"pending": True, "mode": plan["mode"], "run_id": plan["run_id"], "items": summary,
                "commit_started": plan["commit"]["started"], "steps_todo": len(todo),
                "choices": ["resume"],
                "message": "a commit was interrupted; only resume is offered because the store is half-written"}
    return {"pending": True, "mode": plan["mode"], "run_id": plan["run_id"], "items": summary,
            "choices": ["resume", "discard"]}


def discard(store_root):
    st = status(store_root)
    if not st["pending"]:
        return {"discarded": False, "message": "nothing pending"}
    if "discard" not in st["choices"]:
        raise StoreError("a commit was interrupted; it can only be resumed (spec §9.6)")
    shutil.rmtree(_dir(store_root))
    return {"discarded": True}


# ---------- progress (.state/progress.json) ----------

def progress_start(store_root, mode, target, batch_size=50):
    now = utcnow()
    data = {"schema_version": 1, "run_id": run_id(now), "mode": mode, "target": target,
            "batch_size": batch_size, "batches_done": 0, "done": [], "started": iso(now), "updated": iso(now)}
    write_json(os.path.join(store_root, ".state", "progress.json"), data, "progress")
    return data


def progress_batch_done(store_root, paths):
    p = os.path.join(store_root, ".state", "progress.json")
    data = read_store_file(p, "progress")
    data["done"] = sorted(set(data["done"]) | set(paths))
    data["batches_done"] += 1
    data["updated"] = iso(utcnow())
    write_json(p, data, "progress")
    return data


def progress_read(store_root, target):
    p = os.path.join(store_root, ".state", "progress.json")
    if not os.path.exists(p):
        return None
    data = read_store_file(p, "progress")
    return data if data["target"] == target else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["status", "discard"])
    a = ap.parse_args(argv)
    try:
        out = status(a.store) if a.action == "status" else discard(a.store)
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
