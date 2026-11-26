import re


def normalize_phone(value):
    """Xalqaro formatdagi raqamni qaytaradi, noto'g'ri bo'lsa None."""
    phone = re.sub(r"[\s\-()]", "", value)
    return phone if re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) else None
