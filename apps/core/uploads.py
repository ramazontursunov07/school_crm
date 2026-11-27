"""Yuklanadigan fayllarni tekshirish.

Foydalanuvchi aytgan `Content-Type` va fayl nomiga ishonilmaydi: kengaytma
ruxsat etilgan ro'yxatda bo'lishi va faylning boshidagi baytlar (signatura)
kengaytmaga mos kelishi kerak. Faylni diskka saqlashda asl nom ishlatilmaydi:
`storage_name()` tasodifiy nom beradi (path traversal va ustiga yozishdan
himoya).

Ishlatish (serializer yoki view ichida)::

    validate_upload(request.FILES["file"], kinds=("image", "document"))
    path = default_storage.save(storage_name(file.name), file)

Cheklov: rasm to'liq dekodlanmaydi (Pillow yo'q), faqat signatura tekshiriladi.
Antivirus tekshiruvi yo'q (9-bosqich).
"""

import os
import re
import uuid
import zipfile

from rest_framework.exceptions import ValidationError

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_FILENAME_LENGTH = 150
# Zip ichidagi (docx/xlsx) umumiy hajm va fayllar soni: zip-bomba himoyasi
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000

# Nom ichida uchrasa rad etiladigan kengaytmalar (masalan `rasm.php.jpg`)
DANGEROUS_EXTENSIONS = frozenset(
    {
        ".php", ".phtml", ".py", ".pyc", ".js", ".mjs", ".html", ".htm", ".svg",
        ".exe", ".dll", ".bat", ".cmd", ".com", ".msi", ".sh", ".ps1", ".vbs",
        ".jar", ".jsp", ".asp", ".aspx", ".cgi", ".pl", ".rb", ".scr", ".lnk",
    }
)

_ZIP = (b"PK\x03\x04",)
# kengaytma -> (tur, signaturalar)
SIGNATURES = {
    ".jpg": ("image", (b"\xff\xd8\xff",)),
    ".jpeg": ("image", (b"\xff\xd8\xff",)),
    ".png": ("image", (b"\x89PNG\r\n\x1a\n",)),
    ".webp": ("image", (b"RIFF",)),  # qo'shimcha: 8-11 baytlar `WEBP`
    ".pdf": ("document", (b"%PDF-",)),
    ".docx": ("document", _ZIP),
    ".xlsx": ("document", _ZIP),
}
_OFFICE_REQUIRED = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
}

_HEADER_SIZE = 16


def _fail(message):
    raise ValidationError({"file": [message]})


def safe_original_name(name):
    """Faqat ko'rsatish uchun tozalangan nom (diskka yozish uchun emas)."""
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:MAX_FILENAME_LENGTH]


def storage_name(original_name, subdir="uploads"):
    """Diskka yozish uchun tasodifiy nom. Kengaytma ro'yxatdan olinadi."""
    ext = os.path.splitext(safe_original_name(original_name))[1].lower()
    if ext not in SIGNATURES:
        raise ValueError("Ruxsat etilmagan kengaytma.")
    return f"{subdir}/{uuid.uuid4().hex}{ext}"


def validate_upload(file, *, kinds=("image", "document"), max_size=MAX_FILE_SIZE):
    """Faylni tekshiradi. Xato bo'lsa DRF ValidationError ko'taradi.

    `kinds`: ruxsat etilgan turlar ("image", "document")."""
    if file is None:
        _fail("Fayl yuborilmadi.")
    name = file.name or ""
    if "\x00" in name or len(name) > 255:
        _fail("Fayl nomi noto'g'ri.")
    clean_name = safe_original_name(name)
    if not clean_name:
        _fail("Fayl nomi noto'g'ri.")

    root, ext = os.path.splitext(clean_name.lower())
    entry = SIGNATURES.get(ext)
    if entry is None or entry[0] not in kinds:
        _fail("Bu turdagi faylni yuklab bo'lmaydi.")
    # `a.php.jpg` kabi nomlar: ichki kengaytma xavfli bo'lsa rad etiladi
    inner = {e.lower() for e in re.findall(r"\.[a-z0-9]+", root)}
    if inner & DANGEROUS_EXTENSIONS:
        _fail("Fayl nomi shubhali.")

    size = getattr(file, "size", None)
    if size is None or size <= 0:
        _fail("Fayl bo'sh.")
    if size > max_size:
        _fail(f"Fayl hajmi {max_size // (1024 * 1024)} MB dan oshmasin.")

    file.seek(0)
    header = file.read(_HEADER_SIZE)
    file.seek(0)
    if not any(header.startswith(sig) for sig in entry[1]):
        _fail("Fayl tarkibi kengaytmasiga mos emas.")
    if ext == ".webp" and header[8:12] != b"WEBP":
        _fail("Fayl tarkibi kengaytmasiga mos emas.")
    if ext in _OFFICE_REQUIRED:
        _check_office_zip(file, _OFFICE_REQUIRED[ext])
    return clean_name


def _check_office_zip(file, required_member):
    try:
        with zipfile.ZipFile(file) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if len(infos) > MAX_ZIP_ENTRIES:
                _fail("Fayl tarkibi noto'g'ri.")
            if sum(info.file_size for info in infos) > MAX_ZIP_UNCOMPRESSED:
                _fail("Fayl tarkibi noto'g'ri.")
            if required_member not in names or "[Content_Types].xml" not in names:
                _fail("Fayl tarkibi kengaytmasiga mos emas.")
            # Makro (VBA) saqlaydigan fayllar rad etiladi
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                _fail("Makroli fayllar qabul qilinmaydi.")
            if any(n.startswith(("/", "\\")) or ".." in n.split("/") for n in names):
                _fail("Fayl tarkibi noto'g'ri.")
    except zipfile.BadZipFile:
        _fail("Fayl buzilgan.")
    finally:
        file.seek(0)
        