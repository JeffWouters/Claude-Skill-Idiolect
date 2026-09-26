"""Writer bands (design: decision log, after runs 5 and 6): the check's tolerance follows how much the
writer's own passages vary, and never gets narrower than the global band."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "idiolect" / "scripts"))

import check  # noqa: E402
import measure  # noqa: E402


def para(sentence, n):
    return " ".join([sentence] * n)


def text(k):
    """Four paragraphs of about 100 words; odd k uses semicolons, even k none."""
    s = "The road ran on; we followed it past the mill and the pond." if k % 2 else \
        "The road ran on and we followed it past the mill and the pond."
    return "\n\n".join(para(s, 8) for _ in range(4))


def test_few_windows_keep_the_global_bands():
    texts = [text(k) for k in range(3)]
    vals = measure.metrics("\n\n".join(texts))
    b = measure.writer_bands(texts, "en", vals)
    assert all(b[m] == (measure.METRICS[m]["overshoot"], measure.METRICS[m]["shortfall"]) for m in b)


def test_many_windows_widen_and_never_narrow():
    texts = [text(k) for k in range(2 * measure.BAND_MIN_WINDOWS)]
    assert len(measure.windows(texts)) >= measure.BAND_MIN_WINDOWS
    vals = measure.metrics("\n\n".join(texts))
    b = measure.writer_bands(texts, "en", vals)
    for m, (o, s) in b.items():
        assert o >= measure.METRICS[m]["overshoot"] and s <= measure.METRICS[m]["shortfall"]
    # half the writer's own passages have no semicolon: a draft without one is not a shortfall
    assert b["semicolons_per_1k"][1] == measure.NO_SHORTFALL
    fpm = {"value": vals["semicolons_per_1k"], "overshoot": b["semicolons_per_1k"][0],
           "shortfall": b["semicolons_per_1k"][1], "primary": False}
    assert check.flag_metric("semicolons_per_1k", 0.0, vals["semicolons_per_1k"], fpm)[0] == "ok"
    glob = {**fpm, "overshoot": measure.METRICS["semicolons_per_1k"]["overshoot"],
            "shortfall": measure.METRICS["semicolons_per_1k"]["shortfall"]}
    assert check.flag_metric("semicolons_per_1k", 0.0, vals["semicolons_per_1k"], glob)[0] == "shortfall"
