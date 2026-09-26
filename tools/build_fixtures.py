#!/usr/bin/env python3
"""Split public-domain essay collections from Project Gutenberg into fixture texts.

    python3 tools/build_fixtures.py <folder with pgNNNN.txt files> [author,author]
    python3 tools/build_fixtures.py --later <folder with pgNNNN.txt files> [author,author]

Writes evals/fixtures/<author>/<nn>-<slug>.md, one essay per file, with frontmatter
naming the source. With --later, writes the LATER books to evals/holdouts-later/<author>/:
held-out text from other books by the same author, never learned (evaluation runs 5 and 6). Only authors who died before 1956 (public domain in the US and
the EU) and books first published before 1929 are used.
"""
import re
import sys
import pathlib
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "fixtures"

BOOKS = {
    "alexander-smith": {"name": "Alexander Smith", "died": 1867, "books": [
        (18135, "Dreamthorp", 1863, ["DREAMTHORP", "ON THE WRITING OF ESSAYS", "OF DEATH AND THE FEAR OF DYING",
                                     "WILLIAM DUNBAR", "A LARK'S FLIGHT", "CHRISTMAS", "MEN OF LETTERS",
                                     "ON THE IMPORTANCE OF A MAN TO HIMSELF", "A SHELF IN MY BOOKCASE",
                                     "GEOFFREY CHAUCER", "BOOKS AND GARDENS", "ON VAGABONDS"])]},
    "alice-meynell": {"name": "Alice Meynell", "died": 1922, "books": [
        (1276, "The Rhythm of Life, and Other Essays", 1893,
         ["THE RHYTHM OF LIFE", "DECIVILISED", "A REMEMBRANCE", "THE SUN", "THE FLOWER", "UNSTABLE EQUILIBRIUM",
          "THE UNIT OF THE WORLD", "BY THE RAILWAY SIDE", "POCKET VOCABULARIES", "PATHOS", "THE POINT OF HONOUR",
          "COMPOSURE", "DR. OLIVER WENDELL HOLMES", "JAMES RUSSELL LOWELL", "DOMUS ANGUSTA", "REJECTION",
          "THE LESSON OF LANDSCAPE", "MR. COVENTRY PATMORE'S ODES", "INNOCENCE AND EXPERIENCE",
          "PENULTIMATE CARICATURE"]),
        (1205, "The Colour of Life", 1896,
         ["THE COLOUR OF LIFE", "A POINT OF BIOGRAPHY", "CLOUD", "WINDS OF THE WORLD", "THE HONOURS OF MORTALITY",
          "AT MONASTERY GATES", "RUSHES AND REEDS", "ELEONORA DUSE", "DONKEY RACES", "GRASS", "A WOMAN IN GREY",
          "SYMMETRY AND INCIDENT", "THE ILLUSION OF HISTORIC TIME", "EYES"])]},
    "samuel-mcchord-crothers": {"name": "Samuel McChord Crothers", "died": 1927, "books": [
        (73172, "The Pardoner's Wallet", 1905,
         ["THE PARDONER", "UNSEASONABLE VIRTUES", "AN HOUR WITH OUR PREJUDICES", "HOW TO KNOW THE FALLACIES",
          "THE DIFFICULTIES OF THE PEACEMAKERS", "THE LAND OF THE LARGE AND CHARITABLE AIR",
          "A COMMUNITY OF HUMORISTS", "A SAINT RECANONIZED", "AS HE SEES HIMSELF", "A MAN UNDER ENCHANTMENT",
          "THE CRUELTY OF GOOD PEOPLE"])]},
    "arthur-christopher-benson": {"name": "Arthur Christopher Benson", "died": 1925, "books": [
        (4614, "From a College Window", 1906,
         ["THE POINT OF VIEW", "ON GROWING OLDER", "BOOKS", "SOCIABILITIES", "CONVERSATION", "BEAUTY", "VIII",
          "EGOTISM", "EDUCATION", "AUTHORSHIP", "THE CRITICISM OF OTHERS", "PRIESTS", "XIII", "AMBITION",
          "THE SIMPLE LIFE", "GAMES", "SPIRITUALISM", "XVII", "HABITS", "XVIII", "RELIGION"])]},
    "agnes-repplier": {"name": "Agnes Repplier", "died": 1950, "books": [
        (59430, "Essays in Idleness", 1893,
         ["AGRIPPINA.", "THE CHILDREN’S POETS.", "THE ELF AND THE BUMBLE BEE.", "THE PRAISES OF WAR.",
          "LEISURE.", "WORDS.", "ENNUI.", "WIT AND HUMOR.", "LETTERS.", "ANN DORSET, PEMBROKE AND MONTGOMERY."])]},
    "charles-dudley-warner": {"name": "Charles Dudley Warner", "died": 1900, "books": [
        (3134, "Backlog Studies", 1873,
         ["FIRST STUDY", "SECOND STUDY", "THIRD STUDY", "FOURTH STUDY", "FIFTH STUDY", "SIXTH STUDY",
          "SEVENTH STUDY", "EIGHTH STUDY", "NINTH STUDY", "TENTH STUDY", "ELEVENTH STUDY"])]},
    "robert-cortes-holliday": {"name": "Robert Cortes Holliday", "died": 1947, "clean": 2, "books": [
        (13708, "Walking-Stick Papers", 1918,
         ["ON CARRYING A CANE", "THE FISH REPORTER", "ON GOING A JOURNEY", "GOING TO ART EXHIBITIONS",
          "A ROUNDABOUT PAPER", "THAT REVIEWER \"CUSS\"", "LITERARY LEVITIES IN LONDOW|LITERARY LEVITIES IN LONDON", "HENRY JAMES, HIMSELF",
          "MEMORIES OF A MANUSCRIPT", "\"YOU ARE AN AMERICAN\"", "WHY MEN CAN'T READ NOVELS BY WOMEN",
          "THE DESSERT OF LIFE", "A CLERK MAY LOOK AT A CELEBRITY", "CAUN'T SPEAK THE LANGUAGE",
          "HUNTING LODGINGS", "MY FRIEND, THE POLICEMAN", "HELP WANTED--MALE, FEMALE", "HUMAN MUNICIPAL DOCUMENTS",
          "AS TO PEOPLE", "HUMOURS OP THE BOOK SHOP|HUMOURS OF THE BOOK SHOP", "THE DECEASED", "A TOWN CONSTITUTIONAL",
          "READING AFTER THIRTY", "ON WEARING A HAT"])]},
    "katharine-fullerton-gerould": {"name": "Katharine Fullerton Gerould", "died": 1944, "clean": 2, "books": [
        (78310, "Modes and Morals", 1920,
         ["THE NEW SIMPLICITY", "DRESS AND THE WOMAN", "CAVIARE ON PRINCIPLE", "THE EXTIRPATION OF CULTURE",
          "FASHIONS IN MEN", "THE NEWEST WOMAN", "TABU AND TEMPERAMENT", "THE BOUNDARIES OF TRUTH",
          "MISS ALCOTT’S NEW ENGLAND", "THE SENSUAL EAR", "BRITISH NOVELISTS, LTD.",
          "THE REMARKABLE RIGHTNESS OF RUDYARD KIPLING", "FOOTNOTES:"])]},
}

# Other essay books by fixture authors, held out for the confirming runs (design: decision log). Never
# learned: they live outside evals/fixtures/, which is the learning source.
LATER = {
    "robert-cortes-holliday": {"name": "Robert Cortes Holliday", "died": 1947, "clean": 3, "books": [
        (36085, "Turns about Town", 1921,
         ["THE HOTEL GUEST", "A HUMORIST MISFITS AT A MURDER TRIAL", "QUEER THING, 'BOUT UNDERTAKERS' SHOPS",
          "THE HAIR CUT THAT WENT TO MY HEAD", "SEEING MR. CHESTERTON", "WHEN IS A GREAT CITY A SMALL VILLAGE?",
          "THE UNUSUALNESS OF PARISIAN PHILADELPHIA", "OUR LAST SOCIAL ENGAGEMENT AS A FINE ART", "WRITING IN ROOMS",
          "TAKING THE AIR IN SAN FRANCISCO", "BIDDING MR. CHESTERTON GOOD-BYE", "NO SYSTEM AT ALL TO THE HUMAN SYSTEM",
          "SEEING THE \"SITUATIONS WANTED\" SCENE", "LITERARY LIVES", "SO VERY THEATRICAL",
          "OUR STEEPLEJACK OF THE SEVEN ARTS", "FORMER TENANT OF HIS ROOM", "ONLY SHE WAS THERE",
          "A HUMORIST'S NOTE-BOOK", "INCLUDING STUDIES OF TRAFFIC \"COPS\"", "THREE WORDS ABOUT LITERATURE",
          "RECOLLECTIONS OF LANDLADIES", "AN IDIOSYNCRASY", "THE SEXLESS CAMERA", "I KNOW AN EDITOR",
          "A DIP INTO THE UNDERWORLD", "NOSING 'ROUND WASHINGTON", "FAME: A STORY OF AMERICAN LITERATURE"])]},
    "samuel-mcchord-crothers": {"name": "Samuel McChord Crothers", "died": 1927, "clean": 3, "books": [
        (15866, "Humanly Speaking", 1912,
         ["HUMANLY SPEAKING", "IN THE HANDS OF A RECEIVER", "THE CONTEMPORANEOUSNESS OF ROME",
          "THE AMERICAN TEMPERAMENT", "THE UNACCUSTOMED EARS OF EUROPE", "THE TORYISM OF TRAVELERS",
          "THE OBVIOUSNESS OF DICKENS", "THE SPOILED CHILDREN OF CIVILIZATION", "ON REALISM AS AN INVESTMENT",
          "TO A CITIZEN OF THE OLD SCHOOL", "THE END"])]},
}
LATER_OUT = ROOT / "evals" / "holdouts-later"

MIN_WORDS = 400
# Section markers that end the previous essay but are not essays themselves.
NOT_ESSAYS = {"FOOTNOTES:", "THE END", "FAME: A STORY OF AMERICAN LITERATURE"}


def body_of(raw):
    t = raw.replace("\r\n", "\n").lstrip("﻿")
    s = t.find("*** START")
    e = t.find("*** END")
    return t[t.find("\n", s) + 1:e]


def is_heading_line(lines, i, title):
    return lines[i].strip() == title and (i == 0 or not lines[i - 1].strip())


def clean(text, version=1):
    """version 1 built the original authors; version 2 (authors marked "clean": 2) also handles italics
    across a line break, small caps and part markers. Rebuilding an author with its own version gives
    the same texts and hashes."""
    text = re.sub(r"\[Illustration[^\]]*\]", "", text)
    text = re.sub(r"\[(\d+|[A-Z])\]", "", text)                 # footnote markers
    text = re.sub(r"(?m)^\s*\[?Footnote.*$", "", text)
    if version >= 3:
        text = re.sub(r"(?m)^\s*CHAPTER [IVXL]+\s*$", "", text)       # chapter labels above titles
    if version >= 2:
        text = re.sub(r"_([^_\n]+(?:\n[^_\n]+)?)_", r"\1", text)    # PG italics, also across one line break
        text = re.sub(r"\+([^+\n]+)\+", r"\1", text)                 # PG small caps
        text = re.sub(r"(?m)^\s*(?:PROLOGUE|EPILOGUE|[IVXL]{1,6})\s*$", "", text)   # part and chapter markers
    else:
        text = re.sub(r"_([^_\n]+)_", r"\1", text)                    # PG italics
    text = re.sub(r"(?im)^\s*end of (the )?project gutenberg.*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in text.split("\n\n")]
    return "\n\n".join(p for p in paras if p)


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "untitled"


def main(src, only=None, later=False):
    src = pathlib.Path(src)
    total = 0
    out_root = LATER_OUT if later else OUT
    for author, meta in (LATER if later else BOOKS).items():
        if only and author not in only:
            continue
        n = 0
        (out_root / author).mkdir(parents=True, exist_ok=True)
        for pg, book, year, titles in meta["books"]:
            lines = body_of((src / f"pg{pg}.txt").read_text(encoding="utf-8")).split("\n")
            # take the LAST standalone occurrence of each title (the first ones are title page / contents)
            pos = []
            for entry in titles:
                title, _, shown = entry.partition("|")    # "HEADING|Name" where the source has a typo
                hits = [i for i in range(len(lines)) if is_heading_line(lines, i, title)]
                if not hits:
                    print(f"  ! {author}: heading not found: {title}")
                    continue
                pos.append((hits[-1], shown or title))
            pos.sort()
            for k, (i, title) in enumerate(pos):
                end = pos[k + 1][0] if k + 1 < len(pos) else len(lines)
                if title in NOT_ESSAYS:
                    continue
                text = clean("\n".join(lines[i + 1:end]), meta.get("clean", 1))
                words = len(text.split())
                if words < MIN_WORDS:
                    continue
                n += 1
                name = title.title().rstrip(".") if not re.fullmatch(r"[IVXL]+", title) else f"Chapter {title}"
                fm = (f"---\nauthor: {meta['name']}\nauthor_died: {meta['died']}\nbook: \"{book}\"\n"
                      f"first_published: {year}\ntitle: \"{name}\"\nsource: https://www.gutenberg.org/ebooks/{pg}\n"
                      f"licence: public domain (US and EU)\nwords: {words}\n---\n\n")
                (out_root / author / f"{n:02d}-{slug(name)}.md").write_text(fm + text + "\n", encoding="utf-8")
        print(f"{author}: {n} essays")
        total += n
    print(f"total {total}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--later"]
    main(args[0], set(args[1].split(",")) if len(args) > 1 else None, later="--later" in sys.argv[1:])
