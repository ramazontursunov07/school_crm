"""Kodlarni yuborish. Email Django orqali; SMS provayderi 8-bosqichda ulanadi."""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

SUBJECT = "School CRM: tasdiqlash kodi"


def _message(code):
    return (
        f"School CRM tasdiqlash kodi: {code}\n"
        "Kod 10 daqiqa amal qiladi. Uni hech kimga aytmang. "
        "Agar kodni siz so'ramagan bo'lsangiz, bu xabarni e'tiborsiz qoldiring."
    )


def send_code(*, target, code):
    """Kodni yuboradi. Yuborilgan bo'lsa True, bo'lmasa False qaytaradi."""
    if "@" in target:
        return _send_email(target, code)
    return _send_sms(target, code)


def _send_email(email, code):
    try:
        send_mail(SUBJECT, _message(code), None, [email])
    except Exception:
        logger.exception("Tasdiqlash emailini yuborib bo'lmadi")
        return False
    return True


def _send_sms(phone, code):
    if settings.DEBUG:
        # Faqat lokal ishlab chiqish uchun: haqiqiy SMS yuborilmaydi
        logger.info("SMS (sinov) %s: %s", phone, _message(code))
        return True
    # TODO(8-bosqich): SMS provayderi. Kod hech qachon logga yozilmaydi.
    logger.error("SMS provayderi ulanmagan, kod yuborilmadi.")
    return False
