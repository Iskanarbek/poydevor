from django.utils import translation

from poydevor.i18n.engine import LANGUAGES, translate_html

COOKIE = "lang"


class LanguageMiddleware:
    """Reads the chosen language (cookie), activates it for dates/numbers, and translates the page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = request.COOKIES.get(COOKIE)
        lang = lang if lang in LANGUAGES else "uz"
        request.LANGUAGE_CODE = lang
        translation.activate(lang)
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
        if (
            lang != "uz" and not getattr(response, "streaming", False)
            and response.get("Content-Type", "").startswith("text/html") and response.content
        ):
            charset = response.charset or "utf-8"
            response.content = translate_html(response.content.decode(charset), lang).encode(charset)
        return response
