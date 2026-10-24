import io

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from PIL import Image

from poydevor.middleware import MediaSecurityHeadersMiddleware
from poydevor.upload_safety import validate_pdf_or_jpg


def make_jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "JPEG")
    return buffer.getvalue()


def make_png():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "PNG")
    return buffer.getvalue()


JPEG = make_jpeg()
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /OpenAction [3 0 R /Fit] >>\nendobj\n%%EOF"


def upload(name, content=b"data"):
    return SimpleUploadedFile(name, content, content_type="application/octet-stream")


def refused(test, name, content):
    with test.assertRaises(forms.ValidationError) as caught:
        validate_pdf_or_jpg(upload(name, content))
    return caught.exception.messages[0]


class AcceptsRealPdfAndJpgTests(SimpleTestCase):
    def test_real_pdf_and_jpg_are_accepted(self):
        for name, content in [
            ("plan.pdf", PDF), ("photo.jpg", JPEG), ("photo.jpeg", JPEG),
            ("UPPER.PDF", PDF), ("UPPER.JPG", JPEG), ("my.report.v2.pdf", PDF), ("Чертёж.pdf", PDF),
        ]:
            with self.subTest(name=name):
                validate_pdf_or_jpg(upload(name, content))

    def test_pdf_that_opens_to_a_zoom_level_is_not_mistaken_for_dangerous(self):
        validate_pdf_or_jpg(upload("plan.pdf", PDF))   # PDF contains /OpenAction

    def test_pdf_with_leading_blank_line_is_accepted(self):
        validate_pdf_or_jpg(upload("plan.pdf", b"\n" + PDF))


class RefusesEverythingElseTests(SimpleTestCase):
    def test_other_file_types_are_refused_with_a_helpful_message(self):
        for name in [
            "photo.png", "photo.gif", "photo.webp", "drawing.dwg", "model.skp", "brief.docx", "budget.xlsx",
            "deck.pptx", "pack.zip", "pack.rar", "clip.mp4", "notes.txt", "setup.exe", "app.apk", "run.bat",
            "x.js", "page.html", "logo.svg", "macro.docm", "noextension",
        ]:
            with self.subTest(name=name):
                message = refused(self, name, b"harmless text")
                self.assertIn("PDF yoki JPG", message)
                self.assertIn(name, message)

    def test_extension_tricks_do_not_help(self):
        for name in ["setup.exe.", "setup.exe ", "photo.jpg.exe", "photo.pdf.html", "invoice.php"]:
            with self.subTest(name=name):
                refused(self, name, JPEG)

    def test_right_to_left_trick_in_the_name_is_refused(self):
        refused(self, "photo‮gpj.exe", JPEG)
        refused(self, "photo‮.jpg", JPEG)


class RefusesDisguisedFilesTests(SimpleTestCase):
    """A file called .pdf or .jpg must really be one."""

    def test_programs_renamed_to_pdf_or_jpg(self):
        for name in ["plan.pdf", "photo.jpg", "photo.jpeg"]:
            for body in [b"MZ\x90\x00\x03\x00\x00\x00", b"\x7fELF\x02\x01\x01", b"\xcf\xfa\xed\xfe\x07\x00", b"#!/bin/sh\nrm -rf ~"]:
                with self.subTest(name=name, body=body[:4]):
                    refused(self, name, body)

    def test_web_page_or_php_renamed(self):
        for name, body in [
            ("photo.jpg", b"<html><script>steal()</script></html>"),
            ("plan.pdf", b"<?php system($_GET[1]); ?>"),
            ("photo.jpeg", b"<svg onload=alert(1)>"),
        ]:
            with self.subTest(name=name):
                refused(self, name, body)

    def test_zip_or_apk_renamed_to_pdf_or_jpg(self):
        for name in ["plan.pdf", "photo.jpg"]:
            with self.subTest(name=name):
                refused(self, name, b"PK\x03\x04 AndroidManifest.xml classes.dex")

    def test_png_renamed_to_jpg(self):
        refused(self, "photo.jpg", make_png())

    def test_jpg_renamed_to_pdf_and_pdf_renamed_to_jpg(self):
        refused(self, "plan.pdf", JPEG)
        refused(self, "photo.jpg", PDF)

    def test_broken_jpeg_that_only_starts_like_one(self):
        refused(self, "photo.jpg", b"\xff\xd8\xff\xe0" + b"garbage" * 20)

    def test_empty_files(self):
        refused(self, "plan.pdf", b"")
        refused(self, "photo.jpg", b"")


class RefusesDangerousPdfsTests(SimpleTestCase):
    def test_pdf_with_javascript_launch_or_hidden_files(self):
        for marker in [b"/JavaScript", b"/JS (app.alert(1))", b"/Launch", b"/EmbeddedFile", b"/RichMedia"]:
            with self.subTest(marker=marker):
                refused(self, "plan.pdf", b"%PDF-1.4\n1 0 obj << " + marker + b" >> endobj\n%%EOF")

    def test_marker_split_across_the_read_boundary_is_still_found(self):
        body = b"%PDF-1.4\n" + b"x" * (1024 * 1024 - 14) + b"/JavaScript" + b" endobj"
        refused(self, "plan.pdf", body)


class SizeAndFileStateTests(SimpleTestCase):
    def test_too_big_is_refused_with_the_limit_in_the_message(self):
        big = upload("plan.pdf", PDF + b"x" * (2 * 1024 * 1024))
        with self.assertRaises(forms.ValidationError) as caught:
            validate_pdf_or_jpg(big, max_mb=2)
        self.assertIn("2 MB", caught.exception.messages[0])

    def test_within_the_limit_is_fine(self):
        validate_pdf_or_jpg(upload("plan.pdf", PDF), max_mb=2)

    def test_file_position_is_reset_so_saving_still_works(self):
        for name, content in [("plan.pdf", PDF), ("photo.jpg", JPEG)]:
            f = upload(name, content)
            validate_pdf_or_jpg(f, max_mb=5)
            self.assertEqual(f.read(), content)

    def test_file_position_is_reset_even_when_refused(self):
        f = upload("plan.pdf", b"MZ not a pdf")
        with self.assertRaises(forms.ValidationError):
            validate_pdf_or_jpg(f)
        self.assertEqual(f.tell(), 0)


class MediaHeadersTests(SimpleTestCase):
    def serve(self, path):
        middleware = MediaSecurityHeadersMiddleware(lambda request: HttpResponse(b"x"))
        return middleware(RequestFactory().get(path))

    def test_anything_that_is_not_a_photo_pdf_or_video_is_forced_to_download_and_sandboxed(self):
        for path in ["/media/portfolio_files/plan.dwg", "/media/plans/notes.txt", "/media/x/page.html", "/media/x/a%20b.svg"]:
            with self.subTest(path=path):
                response = self.serve(path)
                self.assertEqual(response["Content-Disposition"], "attachment")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertIn("sandbox", response["Content-Security-Policy"])

    def test_photos_and_pdfs_still_open_in_the_browser(self):
        for path in ["/media/a.jpg", "/media/a.JPEG", "/media/a.pdf", "/media/a.png"]:
            with self.subTest(path=path):
                response = self.serve(path)
                self.assertFalse(response.has_header("Content-Disposition"))
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_ordinary_pages_are_untouched(self):
        response = self.serve("/arxitektorlar/")
        self.assertFalse(response.has_header("X-Content-Type-Options"))
        self.assertFalse(response.has_header("Content-Disposition"))


class UploadFormsUseTheCheckTests(TestCase):
    def test_portfolio_project_file_takes_only_real_pdf_or_jpg(self):
        from architects.forms import PortfolioProjectEditForm
        from architects.models import Style
        style = Style.objects.create(name="Zamonaviy")

        def check(name, content):
            form = PortfolioProjectEditForm({"title": "Uy", "style": style.pk}, {"attachment": upload(name, content)})
            return form.is_valid(), form.errors.get("attachment")

        self.assertTrue(check("reja.pdf", PDF)[0])
        self.assertTrue(check("reja.jpg", JPEG)[0])
        for name, content in [("model.skp", b"x"), ("setup.exe", b"MZ"), ("reja.pdf", b"MZ fake"), ("reja.png", make_png())]:
            with self.subTest(name=name):
                valid, errors = check(name, content)
                self.assertFalse(valid)
                self.assertTrue(errors)

    def test_project_file_field_offers_only_pdf_and_jpg_in_the_picker(self):
        from architects.forms import PortfolioProjectEditForm
        accept = PortfolioProjectEditForm().fields["attachment"].widget.attrs["accept"]
        self.assertIn(".pdf", accept)
        self.assertIn(".jpg", accept)
        self.assertNotIn(".dwg", accept)

    def test_order_house_file_takes_only_real_pdf_or_jpg(self):
        from applications.forms import ApplicationForm
        base = {"size_m2": 80, "rooms_count": 3, "location": "Toshkent"}
        for name, content in [("uy.pdf", PDF), ("uy.jpg", JPEG)]:
            form = ApplicationForm(base, {"plan_pdf": upload(name, content)})
            self.assertTrue(form.is_valid(), form.errors)
        for name, content in [("uy.dwg", b"AC1015"), ("uy.apk", b"PK"), ("uy.png", make_png()), ("uy.pdf", b"MZ fake")]:
            form = ApplicationForm(base, {"plan_pdf": upload(name, content)})
            self.assertFalse(form.is_valid(), name)
            self.assertTrue(form.errors.get("plan_pdf"), name)
