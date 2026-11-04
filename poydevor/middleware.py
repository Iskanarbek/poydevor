import os
from urllib.parse import unquote

from django.conf import settings

# Shown inside the browser: photos, PDFs and videos. Anything else is a download.
INLINE_SAFE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".pdf", ".mp4", ".webm", ".mov",
}


class MediaSecurityHeadersMiddleware:
    """Second line of defence for uploaded files (see poydevor/upload_safety.py).

    Whatever a user uploaded is served from our own domain, so a file that a browser
    treats as a web page could run scripts with our site's privileges. For everything
    under MEDIA_URL this tells browsers to: not guess the type (nosniff), download
    anything that is not a photo, PDF or video instead of displaying it, and never run
    scripts from it (sandbox).

    On a real server nginx serves /media/ itself, so the same three rules live in the
    nginx config too (README, "Uploads and safety"); this covers `runserver`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(settings.MEDIA_URL):
            response["X-Content-Type-Options"] = "nosniff"
            extension = os.path.splitext(unquote(request.path))[1].lower()
            if extension not in INLINE_SAFE_EXTENSIONS:
                response["Content-Disposition"] = "attachment"
                response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response


class NoStorePagesMiddleware:
    """Never let a browser keep a copy of a page.

    Every page here depends on who is signed in. When someone logs out and another person
    (or the same person with another account) logs in, the browser's Back button, its
    "restore previous page" and its cache could otherwise show the earlier account's page,
    or a stale redirect, instead of the page that was asked for. Photos, PDFs and the
    site's own static files are left cacheable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        if not (path.startswith(settings.MEDIA_URL) or path.startswith(settings.STATIC_URL)):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
            response["Pragma"] = "no-cache"
        return response


class PasswordRequiredMiddleware:
    """Architects who registered before passwords existed have none. They may still log in with
    their phone number, but every page sends them to "create your password" until they do."""

    ALLOWED = ("/parol/", "/chiqish/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            settings.REQUIRE_ARCHITECT_PASSWORD
            and user is not None and user.is_authenticated and user.role == user.Role.ARCHITECT
            and not user.has_usable_password() and request.path not in self.ALLOWED
            and not request.path.startswith((settings.STATIC_URL, settings.MEDIA_URL))
        ):
            from django.shortcuts import redirect
            return redirect("accounts:set_password")
        return self.get_response(request)
