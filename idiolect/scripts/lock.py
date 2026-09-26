"""Store lock with heartbeat (spec §10).

    python3 lock.py --store S status
    python3 lock.py --store S acquire --mode learn [--profile sam]
    python3 lock.py --store S heartbeat
    python3 lock.py --store S release
"""
import argparse
import datetime as dt
import json
import os
import sys

from common import StoreError, atomic_write, check_schema, iso, parse_iso, utcnow

ABANDONED_AFTER = dt.timedelta(hours=1)
WRITING_MODES = ("learn", "learn-edit", "interview", "forget", "rollback", "prune", "test", "migrate")


class Locked(StoreError):
    """Another run holds a live lock."""


def _path(store_root):
    return os.path.join(store_root, ".state", "lock")


def read(store_root):
    """Returns (lock dict or None, damaged: bool, heartbeat datetime or None)."""
    p = _path(store_root)
    if not os.path.exists(p):
        return None, False, None
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        check_schema("lock", data)
        return data, False, parse_iso(data["heartbeat"])
    except Exception:  # noqa: BLE001 - damaged lock (spec §10.5)
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(p), dt.timezone.utc)
        return None, True, mtime


def state(store_root, now=None):
    """'free', 'held', 'abandoned' or 'damaged' (a damaged lock younger than an hour blocks)."""
    now = now or utcnow()
    data, damaged, hb = read(store_root)
    if data is None and not damaged:
        return "free"
    if now - hb >= ABANDONED_AFTER or hb - now >= ABANDONED_AFTER:
        return "abandoned"  # old, or so far in the future that the clock that wrote it was wrong
    return "damaged" if damaged else "held"


def _pending_exists(store_root):
    return os.path.exists(os.path.join(store_root, ".state", "pending", "plan.json"))


def acquire(store_root, mode, profile=None, now=None):
    """Take the lock. Returns a dict with 'taken_over' and 'pending' (a leftover pending area to
    offer resume/discard for, spec §9.7). Raises Locked when a live lock exists."""
    if mode not in WRITING_MODES:
        raise StoreError(f"{mode} is not a store-writing mode")
    now = now or utcnow()
    os.makedirs(os.path.join(store_root, ".state"), exist_ok=True)
    mine = {"schema_version": 1, "mode": mode, "started": iso(now), "heartbeat": iso(now),
            "pending": _pending_exists(store_root)}
    if profile:
        mine["profile"] = profile
    text = json.dumps(mine) + "\n"
    p = _path(store_root)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return {"taken_over": False, "pending": mine["pending"], "lock": mine}
    except FileExistsError:
        pass
    st = state(store_root, now)
    if st in ("held", "damaged"):
        data, damaged, hb = read(store_root)
        who = "a damaged lock" if damaged else f"{data['mode']} since {data['started']}"
        raise Locked(f"store is locked by {who}; heartbeat {iso(hb)}")
    # abandoned: take over atomically (spec §10.4)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, p)
    back, _, _ = read(store_root)
    if not back or back["started"] != mine["started"] or back["mode"] != mode:
        raise Locked("another run took over the abandoned lock first")
    return {"taken_over": True, "pending": mine["pending"], "lock": mine}


def heartbeat(store_root, now=None):
    data, damaged, _ = read(store_root)
    if data is None:
        raise StoreError("no valid lock to update")
    data["heartbeat"] = iso(now or utcnow())
    data["pending"] = _pending_exists(store_root)
    atomic_write(_path(store_root), json.dumps(data) + "\n")
    return data


def release(store_root):
    p = _path(store_root)
    if os.path.exists(p):
        os.remove(p)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("action", choices=["status", "acquire", "heartbeat", "release"])
    ap.add_argument("--mode")
    ap.add_argument("--profile")
    a = ap.parse_args(argv)
    try:
        if a.action == "status":
            data, damaged, hb = read(a.store)
            out = {"state": state(a.store), "lock": data, "damaged": damaged,
                   "heartbeat": iso(hb) if hb else None}
        elif a.action == "acquire":
            out = acquire(a.store, a.mode, a.profile)
        elif a.action == "heartbeat":
            out = heartbeat(a.store)
        else:
            release(a.store)
            out = {"released": True}
    except Locked as e:
        print(json.dumps({"status": "locked", "message": str(e)}))
        return 3
    except StoreError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
