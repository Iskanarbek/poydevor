from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

from poydevor.i18n.engine import LANGUAGES
from poydevor.i18n.middleware import COOKIE


def set_language(request, code):
    """Remember the visitor's language (a cookie) and go back to where they were."""
    target = request.GET.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = "/"
    response = HttpResponseRedirect(target)
    if code in LANGUAGES:
        response.set_cookie(COOKIE, code, max_age=365 * 24 * 3600, samesite="Lax", secure=request.is_secure())
    return response
