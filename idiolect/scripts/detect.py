"""Language identification and segments (spec §4.4)."""
import collections
import dataclasses

from common import content_hash, count_words

MIN_WORDS = 40
MIN_CONFIDENCE = 0.9
UNSUPPORTED = {"ja", "zh", "th", "lo", "km", "my", "bo"}

_detector = None


def _det():
    global _detector
    if _detector is None:
        from lingua import LanguageDetectorBuilder
        _detector = LanguageDetectorBuilder.from_all_languages().build()
    return _detector


def identify(text):
    """(iso 639-1 code, confidence) of the most likely language, or (None, 0.0)."""
    vals = _det().compute_language_confidence_values(text)
    if not vals:
        return None, 0.0
    top = vals[0]
    return top.language.iso_code_639_1.name.lower(), top.value


@dataclasses.dataclass
class Text:
    key: str        # <hash> or <hash>#n
    lang: str       # detected language of this text (main: may be replaced by a set lang)
    blocks: list

    @property
    def text(self):
        return "\n\n".join(self.blocks)

    @property
    def words(self):
        return count_words(self.text)


def split(blocks, set_lang=None):
    """Split a file's cleaned blocks into the main text and its segments.

    Returns [main, seg2, seg3, ...]. The main text's key is the hash of the whole cleaned text.
    set_lang (from command, manifest entry, rule or frontmatter) replaces the detected main
    language but does not stop segmenting.
    """
    whole = "\n\n".join(blocks)
    h = content_hash(whole)
    detected = []
    for b in blocks:
        if count_words(b) >= MIN_WORDS:
            lang, conf = identify(b)
            detected.append(lang if conf >= MIN_CONFIDENCE else None)
        else:
            detected.append(None)
    by_lang = collections.Counter()
    for b, lang in zip(blocks, detected):
        if lang:
            by_lang[lang] += count_words(b)
    if by_lang:
        # most words; ties broken by first appearance
        order = [lang for lang in detected if lang]
        main = max(by_lang, key=lambda lang: (by_lang[lang], -order.index(lang)))
    else:
        main, _ = identify(whole) if whole.strip() else (None, 0.0)
    main_blocks, segments = [], []
    run_lang, run = None, []

    def close():
        nonlocal run_lang, run
        if run:
            segments.append((run_lang, run))
        run_lang, run = None, []

    for b, lang in zip(blocks, detected):
        if lang and lang != main:
            if run and lang != run_lang:
                close()
            run_lang = lang
            run.append(b)
        else:
            close()
            main_blocks.append(b)
    close()
    texts = [Text(key=h, lang=set_lang or main, blocks=main_blocks)]
    for n, (lang, bl) in enumerate(segments, 2):
        texts.append(Text(key=f"{h}#{n}", lang=lang, blocks=bl))
    return texts
