#!/usr/bin/env python3
"""Build the native-prose fixtures for the language-flavour false-alarm test.

Fetches public-domain essays, articles, feuilletons and letters in German, French and Spanish
from Wikisource and writes one Markdown file per piece to evals/fixtures/native-<lang>/.

Every text in SOURCES is by an author who died before 1956 and was first published before 1929,
so it is in the public domain in the US and the EU.

Usage:
    python3 tools/build_native_fixtures.py                 # fetch (cached) and write all fixtures
    python3 tools/build_native_fixtures.py --lang de       # one language only
    python3 tools/build_native_fixtures.py --probe TITLE --lang fr   # print the cleaned text of a page
    python3 tools/build_native_fixtures.py --links TITLE --lang es   # list the main-namespace links of a page

Wikimedia rate-limits clients: every request sends a User-Agent, pauses one second, and on HTTP 429
waits the Retry-After seconds. Pages are rendered in batches (one parse call transcludes several
pages), and responses are cached (default: ~/.cache/idiolect-native-fixtures) so reruns are cheap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "fixtures"
UA = "IdiolectFixtureBuilder/1.0 (https://github.com/JeffWouters/Claude-Skill-Idiolect)"
LICENCE = "public domain (US and EU)"

# (lang, page title, author, died, book, first published, display title or None)
# The display title defaults to the last part of the page title without a disambiguator.
SOURCES: list[tuple[str, str, str, int, str, int, str | None]] = [
    # ---------------------------------------------------------------- German
    ("de", "Traktat über den Hund", "Kurt Tucholsky", 1935, "Die Weltbühne", 1927, None),
    ("de", "Traktat über Lerm und Geräusch", "Kurt Tucholsky", 1935, "Die Weltbühne", 1927, None),
    ("de", "Was darf die Satire? (Tucholsky)", "Kurt Tucholsky", 1935, "Berliner Tageblatt", 1919, None),
    ("de", "Die Flecke", "Kurt Tucholsky", 1935, "Berliner Volkszeitung", 1919, None),
    ("de", "Der Obermieter", "Kurt Tucholsky", 1935, "Prager Tagblatt", 1922, None),
    ("de", "Der berühmteste Mann der Welt", "Kurt Tucholsky", 1935, "Prager Tagblatt", 1922, None),
    ("de", "Ein deutsches Volkslied", "Kurt Tucholsky", 1935, "Prager Tagblatt", 1922, None),
    ("de", "Vormärz", "Kurt Tucholsky", 1935, "Die Schaubühne", 1914, None),
    ("de", "Wir Negativen (Tucholsky)", "Kurt Tucholsky", 1935, "Die Weltbühne", 1919, None),
    ("de", "Fütterung der Raubtiere", "Kurt Tucholsky", 1935, "Die Weltbühne", 1920, None),
    ("de", "Die Dicken", "Kurt Tucholsky", 1935, "Die Weltbühne", 1921, None),
    ("de", "Der Hund als Untergebener", "Kurt Tucholsky", 1935, "Die Weltbühne", 1922, None),
    ("de", "Zehn Minuten (Tucholsky)", "Kurt Tucholsky", 1935, "Die Weltbühne", 1922, None),
    ("de", "Der Linksdenker", "Kurt Tucholsky", 1935, "Die Weltbühne", 1924, None),
    ("de", "Außenseiter der Gesellschaft (Weltbühne)", "Kurt Tucholsky", 1935, "Die Weltbühne", 1925, None),
    ("de", "Der Namensfimmel", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Berliner auf Reisen", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Alte Filme", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Der politische Rundfunk", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Der Hund und der Blinde", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Herr Schwejk", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Typographisches", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Ein Indianerbuch der Technik", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Siegfried Jacobsohn †", "Kurt Tucholsky", 1935, "Die Weltbühne", 1926, None),
    ("de", "Katzenmutter in Paris", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1926, None),
    ("de", "Der Brötchentanz", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1925, None),
    ("de", "Der sinnlose Film", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1928, None),
    ("de", "Der Katzentrust", "Kurt Tucholsky", 1935, "Vossische Zeitung", 1928, None),
    ("de", "... à la Bratianu", "Carl von Ossietzky", 1938, "Die Weltbühne", 1926, "… à la Bratianu"),
    ("de", "Sexual-Kochbücher (Ossietzky)", "Carl von Ossietzky", 1938, "Die Weltbühne", 1927, None),
    ("de", "Klabund (Ossietzky)", "Carl von Ossietzky", 1938, "Die Weltbühne", 1928, None),
    ("de", "Die Chinesische Mauer", "Karl Kraus", 1936, "Die Fackel", 1909, None),
    ("de", "Peter Altenberg (Grabrede von Karl Kraus)", "Karl Kraus", 1936, "Die Fackel", 1919, "Peter Altenberg"),
    ("de", "Die Straße des Ruhms", "Ludwig Bauer", 1935, "Die Schaubühne", 1905, None),
    # ---------------------------------------------------------------- French
    ("fr", "Propos sur le Bonheur/Bucéphale", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Agir", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Amitié", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Attitudes", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Bonne humeur", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/De l’irrésolution", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Des passions", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Devoir d’être heureux", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Diogène", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Espérance", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Gymnastique", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Faire plaisir", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Hercule", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Dénouer", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Drames", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Du désespoir", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Consolation", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Connais-toi", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Accidents", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Propos sur le Bonheur/Bienveillance", "Alain", 1951, "Propos sur le bonheur", 1925, None),
    ("fr", "Promenades Littéraires (Gourmont)/De la fécondité littéraire", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Les Contes de fées", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/La Femme naturelle", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Renan et l’idée scientifique", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Un homme qui pense", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/Il pleut, il pleut, bergère", "Remy de Gourmont", 1915, "Promenades littéraires", 1904, None),
    ("fr", "Promenades Littéraires (Gourmont)/La beauté de la mer", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "Promenades Littéraires (Gourmont)/L’architecture", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "Promenades Littéraires (Gourmont)/L’adoucissement des mœurs", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "Promenades Littéraires (Gourmont)/Les parchemins du féminisme", "Remy de Gourmont", 1915, "Promenades littéraires", 1906, None),
    ("fr", "La Rentrée (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1898, None),
    ("fr", "Défaite en échelons", "Charles Péguy", 1914, "La Revue blanche", 1898, None),
    ("fr", "Règlement de juges", "Charles Péguy", 1914, "La Revue blanche", 1898, None),
    ("fr", "Service militaire (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1899, None),
    ("fr", "L’Opinion publique (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1899, None),
    ("fr", "Associations (Péguy)", "Charles Péguy", 1914, "La Revue blanche", 1899, None),
    ("fr", "Idées générales", "Octave Mirbeau", 1917, "La Vache tachetée", 1886, None),
    ("fr", "Vers le bonheur", "Octave Mirbeau", 1917, "La Vache tachetée", 1887, None),
    ("fr", "Mon jardinier", "Octave Mirbeau", 1917, "La Vache tachetée", 1893, None),
    ("fr", "Le Concombre fugitif", "Octave Mirbeau", 1917, "La Vache tachetée", 1894, None),
    ("fr", "Explosif et baladeur", "Octave Mirbeau", 1917, "La Vache tachetée", 1894, None),
    ("fr", "En attendant l’omnibus", "Octave Mirbeau", 1917, "La Vache tachetée", 1896, None),
    # ---------------------------------------------------------------- Spanish
    ("es", "Mi religión", "Miguel de Unamuno", 1936, "Mi religión y otros ensayos breves", 1907, None),
    ("es", "Verdad y vida", "Miguel de Unamuno", 1936, "Mi religión y otros ensayos breves", 1908, None),
    ("es", "¡Adentro!", "Miguel de Unamuno", 1936, "Tres ensayos", 1900, None),
    ("es", "La crisis actual del patriotismo español", "Miguel de Unamuno", 1936, "Nuestro Tiempo", 1905, None),
    ("es", "Sobre la tumba de Costa", "Miguel de Unamuno", 1936, "Sobre la tumba de Costa", 1911, None),
    ("es", "Con Don Quijote en Sigüenza", "Miguel de Unamuno", 1936, "El Imparcial", 1916, None),
    ("es", "La Kultura y la cultura", "Miguel de Unamuno", 1936, "La Kultura y la cultura", 1913, None),
    ("es", "El anti-maquetismo", "Miguel de Unamuno", 1936, "Heraldo de Madrid", 1898, None),
    ("es", "Méjico y no México", "Miguel de Unamuno", 1936, "Méjico y no México", 1898, None),
    ("es", "España protegida", "Miguel de Unamuno", 1936, "España protegida", 1918, None),
    ("es", "Confesión de culpa", "Miguel de Unamuno", 1936, "El Día", 1917, None),
    ("es", "De las luchas de nuestros días. La res humana", "Miguel de Unamuno", 1936, "De las luchas de nuestros días", 1920, None),
    ("es", "Nuestra América", "José Martí", 1895, "La Revista Ilustrada de Nueva York", 1891, None),
    ("es", "Vindicación de Cuba", "José Martí", 1895, "Vindicación de Cuba", 1889, None),
    ("es", "La verdad sobre los Estados Unidos", "José Martí", 1895, "Patria", 1894, None),
    ("es", "Karl Marx (José Martí)", "José Martí", 1895, "La Nación", 1883, None),
    ("es", "Maestros ambulantes", "José Martí", 1895, "La América", 1884, None),
    ("es", "Educación científica", "José Martí", 1895, "La América", 1883, None),
    ("es", "Mi raza", "José Martí", 1895, "Patria", 1893, None),
    ("es", "La futura esclavitud", "José Martí", 1895, "La América", 1884, None),
    ("es", "A aprender en las haciendas", "José Martí", 1895, "La América", 1883, None),
    ("es", "El tercer año del partido revolucionario cubano", "José Martí", 1895, "Patria", 1894, None),
    ("es", "Prólogo al Poema del Niágara", "José Martí", 1895, "Poema del Niágara", 1882, None),
    ("es", "Carta a Manuel Mercado", "José Martí", 1895, "Cartas", 1895, None),
    ("es", "Granada la bella/01", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Puntos de vista"),
    ("es", "Granada la bella/02", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Lo viejo y lo nuevo"),
    ("es", "Granada la bella/03", "Ángel Ganivet", 1898, "Granada la bella", 1896, "¡Agua!"),
    ("es", "Granada la bella/04", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Luz y sombra"),
    ("es", "Granada la bella/05", "Ángel Ganivet", 1898, "Granada la bella", 1896, "No hay que ensancharse"),
    ("es", "Granada la bella/06", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Nuestro carácter"),
    ("es", "Granada la bella/07", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Nuestro arte"),
    ("es", "Granada la bella/08", "Ángel Ganivet", 1898, "Granada la bella", 1896, "¿Qué somos?"),
    ("es", "Granada la bella/09", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Parrafada filosófica ante una estación de ferrocarril"),
    ("es", "Granada la bella/10", "Ángel Ganivet", 1898, "Granada la bella", 1896, "El constructor espiritual"),
    ("es", "Granada la bella/11", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Monumentos"),
    ("es", "Granada la bella/12", "Ángel Ganivet", 1898, "Granada la bella", 1896, "Lo eterno femenino"),
    ("es", "Cuadros de viaje", "José Ortega y Gasset", 1955, "Artículos (1915)", 1915, None),
    ("es", "La guerra, los pueblos y los dioses", "José Ortega y Gasset", 1955, "Artículos (1915)", 1915, None),
    ("es", "La voluntad del barroco", "José Ortega y Gasset", 1955, "Artículos (1915)", 1915, None),
    ("es", "París nocturno", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Mi domingo de Ramos", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Hombres y pájaros", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Visiones pasadas", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Primavera apolínea", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
    ("es", "Curiosidades literarias", "Rubén Darío", 1916, "Cuentos y crónicas", 1918, None),
]


# ------------------------------------------------------------------------------------ fetching

class Wiki:
    def __init__(self, cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)

    def api(self, lang: str, params: dict, post: bool = False) -> dict:
        params = dict(params, format="json", formatversion="2")
        url = f"https://{lang}.wikisource.org/w/api.php"
        body = urllib.parse.urlencode(params)
        key = hashlib.sha256((url + "?" + body).encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        while True:
            if post:
                req = urllib.request.Request(url, data=body.encode(), headers={"User-Agent": UA})
            else:
                req = urllib.request.Request(url + "?" + body, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.load(resp)
                break
            except urllib.error.HTTPError as err:
                if err.code == 429:
                    wait = int(err.headers.get("Retry-After") or 30)
                    print(f"  429, waiting {wait}s", file=sys.stderr)
                    time.sleep(wait + 1)
                    continue
                raise
        time.sleep(1)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def links(self, lang: str, title: str) -> list[str]:
        data = self.api(lang, {"action": "parse", "page": title, "prop": "links"})
        return [l["title"] for l in data.get("parse", {}).get("links", []) if l["ns"] == 0 and l.get("exists")]

    def render(self, lang: str, titles: list[str], batch: int = 6) -> dict[str, str]:
        """Render pages to HTML, several per parse call, by transcluding them into one text."""
        out: dict[str, str] = {}
        for i in range(0, len(titles), batch):
            group = titles[i:i + batch]
            # a marker paragraph after each page; splitting the HTML string on it (rather than
            # wrapping pages in divs) survives pages that leave a <div> unclosed
            text = "\n\n".join(f"{{{{:{t}}}}}\n\n@@IDIOLECT-SPLIT-{n}@@" for n, t in enumerate(group))
            data = self.api(lang, {"action": "parse", "text": text, "title": "Idiolect fixture",
                                   "contentmodel": "wikitext", "prop": "text", "disablelimitreport": 1,
                                   "disableeditsection": 1}, post=True)
            parts = re.split(r"@@IDIOLECT-SPLIT-(\d+)@@", data["parse"]["text"])
            for k in range(1, len(parts), 2):
                out[group[int(parts[k])]] = parts[k - 1]
        return out


# ------------------------------------------------------------------------------------ cleaning

DROP_SELECTORS = [
    "style", "script", "#textdaten", ".ws-noexport", ".noprint", ".hiddenStructure",
    ".PageNumber", ".pagenum", ".ws-pagenum", "span[class*=pagenum]", ".mw-references-wrap",
    "ol.references", ".references", "sup.reference", ".reference", ".mw-cite-backlink", ".footnote",
    ".footnotes", ".ws-header", ".headertemplate", "#headertemplate", ".ws-summary", ".mw-heading",
    "h1", "h2", "h3", "h4", "h5", "h6", ".poem", ".mw-editsection", ".navigation", ".ws-navigation",
    ".sisitem", ".licenseContainer", ".licence", ".license", "div.center", ".prp-page-qualityheader",
    ".error", ".Z3988", "[style*='display:none']", "[style*='display: none']", ".interProject",
    ".ws-page-nav", ".mw-empty-elt", ".tablenum", ".annotation",
]
CENTER_RE = re.compile(r"text-align:\s*(center|right)", re.I)
# transcription slips in the sources, corrected so that the fixtures read as the author wrote
FIXES = {
    "Earlos Marx": "Carlos Marx",  # drop initial image with the wrong alt text
    "decir ]a verdad": "decir la verdad",
    "die Erscheinungfremd": "die Erscheinung fremd",
}
PARA_END = (".", "!", "?", "…", ":", ";", "“", "”", "»", "«", '"', "—", "–", ")", "’", "'", ",")
SENT_END = (".", "!", "?", "…", ":", "“", "”", "»", "«")
MARKER_RES = [
    re.compile(r"\[(?:…|\.\.\.)\]"),         # editorial [...] for a gap in the source
    re.compile(r"WS: Dieses Bild kann aus urheberrechtlichen Gründen nicht dargestellt werden\.?"),
    re.compile(r"\[\s*\d+\s*\]"),               # [1]
    re.compile(r"\[\s*(?:p\.|S\.|Seite|pág\.)\s*\d+\s*\]", re.I),  # [p. 12]
    re.compile(r"\(\s*\d{1,2}\s*\)(?=[\s.,;:])"),  # (1) after a word
    re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+"),
]


def paragraphs(html: str, title: str = "") -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for sel in DROP_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    # tables: drop info boxes and navigation, keep layout tables that hold the prose
    for tab in soup.find_all("table"):
        if tab.decomposed:
            continue
        if not any(len(p.get_text().split()) >= 30 for p in tab.find_all("p")):
            tab.decompose()
    for el in soup.find_all(style=CENTER_RE):
        el.decompose()
    for el in soup.find_all(["p", "div"], attrs={"align": re.compile("center|right", re.I)}):
        el.decompose()
    # drop initials set as images: keep the letter from the alt text
    for el in soup.select(".dropinitial"):
        img = el.find("img")
        el.replace_with(img.get("alt", "") if img else el.get_text(""))
    # footnote anchors: superscripts that only hold a link to a note
    for sup in soup.find_all("sup"):
        if sup.find("a") or re.fullmatch(r"\W*\d+\W*", sup.get_text()):
            sup.decompose()
    paras: list[str] = []
    for p in soup.find_all("p"):
        for br in p.find_all("br"):
            br.replace_with("\u2028")
        lines = [re.sub(r"\s+", " ", l).strip() for l in p.get_text("").split("\u2028")]
        lines = [l for l in lines if l]
        if len(lines) >= 3 and max(len(l.split()) for l in lines) < 20:
            continue  # verse, address blocks and lists of lines
        # a title or byline set on its own line(s) above the prose in the same paragraph
        while len(lines) > 1 and len(lines[0].split()) <= 8 and not lines[0].endswith(SENT_END):
            lines.pop(0)
        text = " ".join(lines)
        for rx in MARKER_RES:
            text = rx.sub("", text)
        for bad, good in FIXES.items():
            text = text.replace(bad, good)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r" ([,.)])", r"\1", text)
        text = re.sub(r"([(„¿¡]) ", r"\1", text)
        if not text or not re.search(r"\w{2,}", text):
            continue
        if re.fullmatch(r"[\W\d_]*", text):
            continue
        paras.append(text)

    def trim_head(paras: list[str]) -> list[str]:
        while paras and ((len(paras[0].split()) <= 6
                          and (not paras[0].endswith(SENT_END) or re.search(r"\d", paras[0])))
                         or (len(paras[0].split()) <= 10 and not paras[0].endswith(SENT_END))
                         or (len(paras[0].split()) <= 14 and title and title.lower() in paras[0].lower())):
            paras.pop(0)
        return paras

    paras = trim_head(paras)
    # a paragraph cut by a page break in the scan continues in the next one
    joined: list[str] = []
    for text in paras:
        if joined and not joined[-1].endswith(PARA_END):
            prev = joined.pop()
            if re.search(r"\w-$", prev) and text[:1].islower():
                text = prev[:-1] + text  # word hyphenated across the break
            else:
                text = prev + " " + text
        joined.append(text)
    paras = joined
    # signatures, dates and places at the end; title, byline and date lines at the start
    while paras and (len(paras[-1].split()) <= 4
                     or (len(paras[-1].split()) <= 12 and re.search(r"\b1[89]\d\d\b", paras[-1]))):
        paras.pop()
    paras = trim_head(paras)
    return paras


# ------------------------------------------------------------------------------------ output

def display_title(page: str) -> str:
    t = page.rsplit("/", 1)[-1]
    return re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()


def slugify(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ß", "ss").replace("œ", "oe").replace("æ", "ae")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:48].rstrip("-") or "text"


def page_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikisource.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="/_(),:!'’")


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(wiki: Wiki, lang: str, min_words: int = 150) -> None:
    items = [s for s in SOURCES if s[0] == lang]
    html = wiki.render(lang, [s[1] for s in items])
    outdir = OUT / f"native-{lang}"
    outdir.mkdir(parents=True, exist_ok=True)
    retired = None
    for old in sorted(outdir.glob("[0-9][0-9]-*.md")):
        # generated output of an earlier run (recognised by its front matter) is moved aside, never deleted
        if f"\nlang: {lang}\n---\n" in old.read_text(encoding="utf-8") and LICENCE in old.read_text(encoding="utf-8"):
            if retired is None:
                import datetime
                stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                retired = OUT.parent / "_to_delete" / f"native-{lang}-{stamp}"
                retired.mkdir(parents=True, exist_ok=True)
            old.rename(retired / old.name)
    written: set[str] = set()
    n = 0
    total = 0
    for _, page, author, died, book, year, title in items:
        title = title or display_title(page)
        paras = paragraphs(html.get(page, ""), title)
        body = "\n\n".join(paras)
        words = len(body.split())
        if words < min_words:
            print(f"  skip {page!r}: {words} words", file=sys.stderr)
            continue
        n += 1
        name = f"{n:02d}-{slugify(title)}.md"
        front = "\n".join([
            "---",
            f"author: {author}",
            f"author_died: {died}",
            f"book: {yaml_str(book)}",
            f"first_published: {year}",
            f"title: {yaml_str(title)}",
            f"source: {page_url(lang, page)}",
            f"licence: {LICENCE}",
            f"words: {words}",
            f"lang: {lang}",
            "---",
        ])
        (outdir / name).write_text(front + "\n\n" + body + "\n", encoding="utf-8")
        written.add(name)
        total += words
        print(f"  {name}: {words}")
    for stale in sorted(outdir.glob("[0-9][0-9]-*.md")):
        if stale.name not in written:
            print(f"  warning: {stale.name} is not from this run; retire it by hand", file=sys.stderr)
    print(f"{lang}: {n} files, {total} words")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", choices=["de", "fr", "es"], action="append")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/idiolect-native-fixtures"))
    ap.add_argument("--probe", metavar="TITLE", help="print the cleaned text of one page")
    ap.add_argument("--links", metavar="TITLE", help="list the existing main-namespace links of one page")
    args = ap.parse_args()
    wiki = Wiki(Path(args.cache))
    langs = args.lang or ["de", "fr", "es"]
    if args.links:
        print("\n".join(wiki.links(langs[0], args.links)))
        return
    if args.probe:
        paras = paragraphs(wiki.render(langs[0], [args.probe])[args.probe], display_title(args.probe))
        print("\n\n".join(paras))
        print(f"\n[{sum(len(p.split()) for p in paras)} words]", file=sys.stderr)
        return
    for lang in langs:
        build(wiki, lang)


if __name__ == "__main__":
    main()
