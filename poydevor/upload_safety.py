"""Which uploaded files the site accepts: PDF and JPG, nothing else.

Both open on every phone and computer without extra apps, and neither can run a program.
A file is accepted only when ALL of these are true:

* its name ends in .pdf, .jpg or .jpeg;
* its content really is that kind of file (a program, web page or archive renamed to
  ".pdf" or ".jpg" is refused, because the first bytes give it away);
* a JPG opens as a real picture;
* a PDF does not carry the parts that make a PDF dangerous (JavaScript, auto-launch,
  hidden embedded files);
* the name has no hidden right-to-left characters that disguise the real extension.

Used by the project-file field (architects/forms.py) and the client's house-file field
(applications/forms.py).
"""
import os
import re

from django import forms
from PIL import Image

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg"}
# What a file picker on a phone or computer should offer (the real check is the one below).
ACCEPT_ATTRIBUTE = ".pdf,.jpg,.jpeg,application/pdf,image/jpeg"

BIDI_AND_CONTROL = set("‪‫‬‭‮⁦⁧⁨⁩‎‏\x00")

JPEG_MAGIC = b"\xff\xd8\xff"
PDF_MAGIC = b"%PDF-"
# Parts of a PDF that can run code or smuggle a program in.
PDF_DANGEROUS = re.compile(rb"/(JavaScript|Launch|EmbeddedFile|RichMedia)\b|/JS\b")


def _fail(message):
    raise forms.ValidationError(message)


def _not_allowed(display):
    return (
        f"«{display}» qabul qilinmaydi. Faqat PDF yoki JPG fayl yuklang "
        "(ular telefonda ham, kompyuterda ham ochiladi)."
    )


def _check_pdf(upload, display):
    upload.seek(0)
    if not upload.read(1024).lstrip().startswith(PDF_MAGIC):
        _fail(f"«{display}» haqiqiy PDF fayl emas. Faylni PDF qilib qayta saqlab yuklang.")
    upload.seek(0)
    tail = b""
    while True:
        chunk = upload.read(1024 * 1024)
        if not chunk:
            break
        if PDF_DANGEROUS.search(tail + chunk):
            _fail(
                f"«{display}» ichida skript yoki yashirin fayl bor (xavfsiz emas). "
                "PDFni qayta eksport qilib (Print to PDF) yuklang."
            )
        tail = chunk[-32:]


def _check_jpg(upload, display):
    upload.seek(0)
    if not upload.read(4).startswith(JPEG_MAGIC):
        _fail(f"«{display}» haqiqiy JPG rasm emas. Rasmni JPG qilib qayta saqlab yuklang.")
    upload.seek(0)
    try:
        with Image.open(upload) as picture:
            picture.verify()
            is_jpeg = picture.format == "JPEG"
    except Exception:  # noqa: BLE001 - any failure to read it as a picture means refuse it
        is_jpeg = False
    if not is_jpeg:
        _fail(f"«{display}» buzilgan yoki haqiqiy JPG rasm emas. Boshqa rasm yuklang.")


def validate_pdf_or_jpg(upload, max_mb=None):
    """Raise forms.ValidationError (in Uzbek, with what to do) unless this is a genuine
    PDF or JPG; return the upload when it is fine."""
    name = getattr(upload, "name", "") or ""
    display = os.path.basename(name)
    if max_mb is not None and upload.size > max_mb * 1024 * 1024:
        _fail(f"«{display}» juda katta (eng ko'pi {max_mb} MB).")
    if any(ch in BIDI_AND_CONTROL for ch in name):
        _fail(f"«{display}» fayl nomida yashirin belgilar bor. Faylni qayta nomlab yuklang.")
    extension = os.path.splitext(name.strip().rstrip(". "))[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        _fail(_not_allowed(display))
    try:
        if extension == ".pdf":
            _check_pdf(upload, display)
        else:
            _check_jpg(upload, display)
    finally:
        upload.seek(0)
    return upload
