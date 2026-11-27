import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from apps.core.uploads import safe_original_name, storage_name, validate_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def make_zip(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for member in members:
            archive.writestr(member, "x")
    return buffer.getvalue()


def upload(name, data):
    return SimpleUploadedFile(name, data)


class ValidateUploadTests(SimpleTestCase):
    def assertRejected(self, name, data, **kwargs):
        with self.assertRaises(ValidationError):
            validate_upload(upload(name, data), **kwargs)

    def test_valid_png_and_pdf(self):
        self.assertEqual(validate_upload(upload("rasm.png", PNG)), "rasm.png")
        validate_upload(upload("hujjat.pdf", b"%PDF-1.7 test"))

    def test_extension_must_match_content(self):
        self.assertRejected("rasm.png", b"%PDF-1.7 test")
        self.assertRejected("hujjat.pdf", PNG)

    def test_disallowed_extensions(self):
        self.assertRejected("a.svg", b"<svg onload=alert(1)/>")
        self.assertRejected("a.html", b"<html></html>")
        self.assertRejected("a.exe", b"MZ" + b"0" * 32)
        self.assertRejected("nomsiz", PNG)

    def test_dangerous_inner_extension(self):
        self.assertRejected("rasm.php.png", PNG)

    def test_empty_and_oversized(self):
        self.assertRejected("a.png", b"")
        self.assertRejected("a.png", PNG, max_size=10)

    def test_kind_restriction(self):
        self.assertRejected("hujjat.pdf", b"%PDF-1.7 test", kinds=("image",))

    def test_webp_needs_webp_marker(self):
        validate_upload(upload("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 "))
        self.assertRejected("a.webp", b"RIFF\x00\x00\x00\x00WAVEfmt ")

    def test_office_files(self):
        good = make_zip(["[Content_Types].xml", "word/document.xml"])
        validate_upload(upload("a.docx", good))
        self.assertRejected("a.docx", b"PK\x03\x04 buzuq")
        self.assertRejected("a.docx", make_zip(["[Content_Types].xml"]))
        macro = make_zip(
            ["[Content_Types].xml", "word/document.xml", "word/vbaProject.bin"]
        )
        self.assertRejected("a.docx", macro)

    def test_file_position_is_reset(self):
        file = upload("a.png", PNG)
        validate_upload(file)
        self.assertEqual(file.read(), PNG)


class NamesTests(SimpleTestCase):
    def test_safe_original_name_strips_path(self):
        self.assertEqual(safe_original_name("../../etc/Foto.JPG"), "Foto.JPG")
        self.assertEqual(safe_original_name("C:\\x\\y.png"), "y.png")

    def test_storage_name_is_random_and_keeps_extension(self):
        first = storage_name("../Foto.JPG")
        self.assertTrue(first.startswith("uploads/") and first.endswith(".jpg"))
        self.assertNotIn("Foto", first)
        self.assertNotEqual(first, storage_name("../Foto.JPG"))

    def test_storage_name_rejects_unknown_extension(self):
        with self.assertRaises(ValueError):
            storage_name("a.exe")
            