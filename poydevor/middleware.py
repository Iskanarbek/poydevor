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
