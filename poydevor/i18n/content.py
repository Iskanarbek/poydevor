"""Machine translation of what people wrote themselves (project titles and descriptions, bios,
reviews, an order's description...). Names, phone numbers and accounts are never passed in.

The provider is Google Cloud Translation; it needs GOOGLE_TRANSLATE_API_KEY. Without a key (or when
the service does not answer) the original text is shown, so the site never breaks. Every translation
is stored once per text and language, so the service is called only the first time."""
import hashlib
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)
_memory = {}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _ask_provider(text: str, lang: str):
    key = getattr(settings, "GOOGLE_TRANSLATE_API_KEY", "")
    if not key:
        return None
    body = urllib.parse.urlencode({"q": text, "target": lang, "format": "text", "key": key}).encode()
    try:
        with urllib.request.urlopen("https://translation.googleapis.com/language/translate/v2", body, timeout=4) as answer:
            data = json.load(answer)
        return data["data"]["translations"][0]["translatedText"]
    except Exception as error:  # noqa: BLE001 - a translation failure must never break a page
        log.warning("translation failed: %s", error)
        return None


def translate_user_text(text, lang: str) -> str:
    """``text`` in the visitor's language, or the original when that is not possible."""
    if not text or lang not in ("uz", "ru", "en") or not str(text).strip():
        return text
    from translations.models import ContentTranslation
    from poydevor.i18n.engine import norm, translate_text
    known = translate_text(norm(str(text)), lang)       # a fixed site text (e.g. a style name): no service needed
    if known is not None:
        return known
    if lang == "uz" or not getattr(settings, "GOOGLE_TRANSLATE_API_KEY", ""):
        return text                                    # Uzbek is what people write; no key = nothing to ask
    source = str(text)
    digest = _hash(source)
    cached = _memory.get((digest, lang))
    if cached is not None:
        return cached
    row = ContentTranslation.objects.filter(source_hash=digest, lang=lang).first()
    if row is not None:
        _memory[(digest, lang)] = row.text
        return row.text
    translated = _ask_provider(source, lang)
    if translated is None:
        return text                                   # try again next time, show the original now
    ContentTranslation.objects.get_or_create(source_hash=digest, lang=lang, defaults={"text": translated})
    _memory[(digest, lang)] = translated
    return translated
