"""Compare an inventory report with an expected one, as spec §5 ("Comparing with an expected report")
defines. Returns a list of differences; empty means they match."""


def compare(actual, expected):
    diffs = []
    exp_rows = {(r["path"], r["key"]): r for r in expected["rows"]}
    act_rows = list(actual["rows"])
    used = set()
    for (path, key), e in sorted(exp_rows.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        match = None
        for i, a in enumerate(act_rows):
            if i in used or a["path"] != path:
                continue
            if key is None or a["key"] == key:
                match = i
                break
        if match is None:
            diffs.append(f"missing row {path} {key or '(any key)'}")
            continue
        used.add(match)
        a = act_rows[match]
        for field in ("result", "words", "lang", "type"):
            if a.get(field) != e.get(field):
                diffs.append(f"{path} {field}: expected {e.get(field)!r}, got {a.get(field)!r}")
    for i, a in enumerate(act_rows):
        if i not in used:
            diffs.append(f"unexpected row {a['path']} {a['key']} ({a['result']})")
    exp_u = {(u["path"], u["key"]) for u in expected["unreachable"]}
    act_u = {(u["path"], u["key"]) for u in actual["unreachable"]}
    for u in sorted(exp_u - act_u):
        diffs.append(f"missing unreachable {u[0]}")
    for u in sorted(act_u - exp_u):
        diffs.append(f"unexpected unreachable {u[0]}")
    return diffs
