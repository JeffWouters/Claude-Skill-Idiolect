"""Phase 6: web pages and connector texts (spec §23)."""
import functools
import glob
import http.server
import json
import threading

import pytest

import connector
import learn
import stage
import web
from common import StoreError
from store import Store
from test_learn import FIX, full_learn, make_store


def essays(n, author="synthetic-noor", start=10):
    out = []
    for f in sorted(glob.glob(str(FIX / author / "[0-9]*.md")))[start:start + n]:
        t = open(f).read()
        out.append(t.split("---", 2)[-1].strip() if t.startswith("---") else t)
    return out


def page(body, date="2026-03-01"):
    paras = "".join(f"<p>{p}</p>\n" for p in body.split("\n\n"))
    return (f"<html><head><title>Sam's blog</title><meta property=\"article:published_time\" content=\"{date}T08:00:00Z\">"
            f"<script>var x = 'never text';</script><style>p{{color:red}}</style></head><body>"
            f"<nav><a href='/'>Home</a> <a href='/about'>About Sam</a></nav>"
            f"<header><h1>Sam writes</h1></header><article><h2>A post</h2>{paras}</article>"
            f"<aside>Subscribe to the newsletter today!</aside><footer>© Acme 2026. All rights reserved.</footer></body></html>")


@pytest.fixture
def site(tmp_path):
    d = tmp_path / "site"
    d.mkdir()
    a, b = essays(2)
    (d / "one.html").write_text(page(a, "2026-03-01"))
    (d / "two.html").write_text(page(b, "2026-04-01"))
    (d / "short.html").write_text(page("Too short to learn from."))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    (d / "feed.xml").write_text(f"<?xml version='1.0'?><rss version='2.0'><channel><title>x</title>"
                                f"<item><link>{base}/one.html</link><pubDate>Sun, 01 Mar 2026 08:00:00 GMT</pubDate></item>"
                                f"<item><link>{base}/two.html</link><pubDate>Wed, 01 Apr 2026 08:00:00 GMT</pubDate></item>"
                                f"<item><link>{base}/short.html</link></item></channel></rss>")
    (d / "sitemap.xml").write_text(f"<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                                   f"<url><loc>{base}/one.html</loc></url><url><loc>{base}/two.html</loc></url></urlset>")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield base
    srv.shutdown()


def test_main_text_leaves_out_navigation_scripts_and_footers(site, tmp_path):
    out = web.fetch(site + "/one.html", out=tmp_path / "w1")
    idx = json.loads((tmp_path / "w1" / "index.json").read_text())
    text = open(idx[0]["file"]).read()
    assert out["kind"] == "page" and idx[0]["date"] == "2026-03-01"
    for gone in ("never text", "About Sam", "Subscribe", "All rights reserved", "Sam's blog", "color:red"):
        assert gone not in text
    first = " ".join(essays(1)[0].split("\n\n")[0].split())
    assert first in text and len(text.split()) > 150


def test_feeds_and_sitemaps_give_their_pages(site, tmp_path):
    f = web.fetch(site + "/feed.xml", out=tmp_path / "feed")
    assert f["kind"] == "feed" and f["pages"] == 3 and f["kept"] == 2
    idx = json.loads((tmp_path / "feed" / "index.json").read_text())
    assert [r.get("date") for r in idx[:2]] == ["2026-03-01", "2026-04-01"] and "skipped" in idx[2]
    s = web.fetch(site + "/sitemap.xml", max_pages=1, out=tmp_path / "sm")
    assert s["kind"] == "sitemap" and s["pages"] == 1


def test_web_and_mail_texts_join_a_learn_run_with_the_writers_ownership(site, tmp_path):
    st = make_store(tmp_path)
    full_learn(tmp_path, st, "noor", "noor")
    web.fetch(site + "/feed.xml", out=tmp_path / "feed")
    idx = [r for r in json.loads((tmp_path / "feed" / "index.json").read_text()) if "file" in r]
    connector.start(st, "noor", "en", "essay")
    with pytest.raises(StoreError, match="never assumed"):
        connector.add(st, idx[0]["file"], "web", "yes")
    connector.add(st, idx[0]["file"], "web", "own", idx[0]["date"], idx[0]["url"])
    connector.add(st, idx[1]["file"], "web", "assisted", idx[1]["date"], idx[1]["url"])
    mail = tmp_path / "mail.txt"
    mail.write_text(essays(1, "synthetic-idris", 0)[0] + "\n\nKind regards,\nSam\n\nOn Mon, Jane wrote:\n> old")
    names = tmp_path / "n.yaml"
    names.write_text("[]\n")
    learn.mail_names(st, names)
    connector.add(st, mail, "mail", "own", note="Re: plan", strip=True)
    learn.do_measure(st)
    stage.Pending(Store(st)).decide(all_decision="approved")
    stage.commit(st)
    s = Store(st)
    ents = list(s.manifest["texts"].items())
    by_origin = {}
    for k, e in ents:
        by_origin.setdefault(e["origin"], []).append((k, e))
    assert len(by_origin["web"]) == 2 and all(e["path"] is None for _, e in by_origin["web"])
    own_web = [e for _, e in by_origin["web"] if e["cached"]]
    assert len(own_web) == 1 and own_web[0]["date"] == "2026-03-01"
    (mk, me), = by_origin["mail"]
    assert me["redaction"]["reviewed"] and "Kind regards" not in s.corpus_text(mk) and "Jane" not in s.corpus_text(mk)
    assert (st / "profiles" / "noor" / "en.essay.json").exists()


def test_code_blocks_are_not_prose_but_inline_code_stays():
    page = ("<html><body><article><p>You manage the current path with the <code>Set-Location</code> cmdlet, "
            "which most people know as cd.</p><pre tabindex=0><code>PS&gt; Set-Location -Path $home\n"
            "PS&gt; Get-Location</code></pre><p>That is all there is to it.</p></article></body></html>")
    text = "\n\n".join(web.main_text(page))
    assert "PS>" not in text and "$home" not in text
    assert "the Set-Location cmdlet" in text and "That is all there is to it." in text


def _guest_run(tmp_path, st):
    out = connector.start(st, "guest", "en", "essay", subject="A guest writer", consent="agreed by mail on 2026-09-27")
    for i, text in enumerate(essays(3, start=0)):
        f = tmp_path / f"p{i}.txt"
        f.write_text(text)
        connector.add(st, f, "web", "own", note=f"https://example.com/{i}")
    return out


def test_a_profile_learned_only_from_web_pages_is_created_in_the_diff_with_its_consent(tmp_path):
    import shutil
    from common import StoreError, read_store_file
    from store import Store
    st = make_store(tmp_path)
    with pytest.raises(StoreError, match="give --subject .* and --consent"):
        connector.start(st, "guest", "en", "essay")
    with pytest.raises(StoreError, match="lower case letters"):
        connector.start(st, "Guest", "en", "essay", subject="A guest writer", consent="agreed by mail")
    other = tmp_path / "other"
    shutil.copytree(st, other)
    assert _guest_run(tmp_path, st)["new_profile"] is True
    p = stage.Pending(Store(st))
    [prof] = [i for i in p.plan["items"] if i["kind"] == "profile"]
    assert "consent: agreed by mail on 2026-09-27" in prof["summary"]
    p.decide(all_decision="approved")
    stage.commit(st)
    data = read_store_file(st / "profiles" / "guest" / "profile.yaml", "profile")
    assert data["subject"] == "A guest writer" and data["consent"] == "agreed by mail on 2026-09-27"
    assert sum(1 for e in Store(st).manifest["texts"].values() if "guest" in e["profiles"]) == 3
    # rejecting the new profile learns nothing for it: its records are dropped at commit
    _guest_run(tmp_path, other)
    p = stage.Pending(Store(other))
    [prof] = [i for i in p.plan["items"] if i["kind"] == "profile"]
    p.decide(reject=[prof["id"]], all_decision="approved")
    stage.commit(other)
    assert not (other / "profiles" / "guest").exists()
    assert not any("guest" in e["profiles"] for e in Store(other).manifest["texts"].values())
