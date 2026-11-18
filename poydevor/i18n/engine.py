"""Translating the site's fixed texts (Uzbek is the source language) into Russian and English.

Pages are written in Uzbek. When a visitor picks another language, the finished HTML page goes
through ``translate_html``: every piece of visible text (and placeholders, tooltips, and the texts
inside the page's small scripts) that is in the catalogue is replaced; everything else — names,
phone numbers, the text people wrote themselves — stays exactly as it is.

Catalogue entries may contain ``{}``: parts that change (a name, a number, a place). Those are
matched as patterns, the changing parts are carried over (and translated too if they are known).
"""
import html
import re
from functools import lru_cache

from poydevor.i18n import catalog_1, catalog_2, catalog_3, catalog_4, catalog_5

LANGUAGES = ("uz", "ru", "en")
_COLUMN = {"ru": 1, "en": 2}


def norm(text: str) -> str:
    text = html.unescape(text)
    for ch in "’‘ʻʼ`´":
        text = text.replace(ch, "'")
    return " ".join(text.split())


@lru_cache(maxsize=None)
def _catalogue(lang: str):
    column = _COLUMN[lang]
    exact, patterns = {}, []
    for module in (catalog_1, catalog_2, catalog_3, catalog_4, catalog_5):
        for entry in module.ENTRIES:
            source, target = norm(entry[0]), entry[column]
            if "{}" in source:
                parts = source.split("{}")
                regex = re.compile("^" + "(.+?)".join(re.escape(p) for p in parts) + "$")
                patterns.append((len(source.replace("{}", "")), regex, target))
            else:
                exact[source] = target
    patterns.sort(key=lambda p: -p[0])        # the most specific pattern first
    return exact, patterns


def translate_text(core: str, lang: str, depth: int = 0):
    """The translation of one piece of text (already normalised), or None when it is not known."""
    if lang not in _COLUMN or not core:
        return None
    exact, patterns = _catalogue(lang)
    found = exact.get(core)
    if found is not None:
        return found
    for _, regex, target in patterns:
        match = regex.match(core)
        if match:
            groups = []
            for group in match.groups():
                translated = translate_text(group, lang, depth + 1) if depth < 2 else None
                groups.append(translated if translated is not None else group)
            pieces = target.split("{}")
            out = pieces[0]
            for index, piece in enumerate(pieces[1:]):
                out += (groups[index] if index < len(groups) else "") + piece
            return out
    return None


# ---- HTML ------------------------------------------------------------------------------------

_TOKEN = re.compile(r"(<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>|<[^>]+>)", re.S)
_ATTR_TEXT = re.compile(r'(\s(?:placeholder|title|alt|aria-label)=)(")([^"]*)(")')
_ATTR_JS = re.compile(r'(\s(?:onsubmit|onclick|x-data|x-text|x-show|x-init|:class|@click|@change|:title|:aria-label)=)(")([^"]*)(")')
_JS_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")


def _text_node(text: str, lang: str) -> str:
    core = text.strip()
    if not core:
        return text
    translated = translate_text(norm(core), lang)
    if translated is None:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()):]
    return lead + html.escape(translated, quote=False) + tail


def _js_literals(source: str, lang: str, quote_in_attribute: bool = False) -> str:
    def replace(match):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        quote = "'" if match.group(1) is not None else '"'
        raw = inner.replace("\\'", "'").replace('\\"', '"')
        translated = translate_text(norm(raw), lang)
        if translated is None:
            return match.group(0)
        lead = raw[: len(raw) - len(raw.lstrip())]
        tail = raw[len(raw.rstrip()):]
        escaped = (lead + translated + tail).replace("\\", "\\\\").replace(quote, "\\" + quote)
        if quote_in_attribute:
            escaped = escaped.replace("&", "&amp;")
        return quote + escaped + quote
    return _JS_LITERAL.sub(replace, source)


def _attr_text(match, lang):
    translated = translate_text(norm(match.group(3)), lang)
    if translated is None:
        return match.group(0)
    return match.group(1) + '"' + html.escape(translated, quote=True) + '"'


def _tag(tag: str, lang: str) -> str:
    tag = _ATTR_TEXT.sub(lambda m: _attr_text(m, lang), tag)
    tag = _ATTR_JS.sub(lambda m: m.group(1) + '"' + _js_literals(m.group(3), lang, True) + '"', tag)
    if tag.lower().startswith("<html"):
        tag = re.sub(r'lang="[^"]*"', f'lang="{lang}"', tag)
    return tag


def translate_html(page: str, lang: str) -> str:
    if lang not in _COLUMN:
        return page
    out = []
    for piece in _TOKEN.split(page):
        if not piece:
            continue
        if piece.startswith("<!--"):
            out.append(piece)
        elif piece.lower().startswith("<script"):
            head_end = piece.index(">") + 1
            out.append(piece[:head_end] + _js_literals(piece[head_end:-9], lang) + piece[-9:])
        elif piece.startswith("<style"):
            out.append(piece)
        elif piece.startswith("<"):
            out.append(_tag(piece, lang))
        else:
            out.append(_text_node(piece, lang))
    return "".join(out)
