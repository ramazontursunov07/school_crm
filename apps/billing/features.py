"""Tarif imkoniyatlari (feature flag'lar) ro'yxati.

Tarifda faqat shu kalitlar bo'lishi mumkin. Yangi imkoniyat qo'shish uchun
shu yerga bitta qator qo'shiladi (migratsiya kerak emas). Tekshiruv
(`plan.has_feature("reports")`) keyingi bosqichlarda, har bir imkoniyat
paydo bo'lganda, shu kalit bo'yicha qilinadi.
"""

from django.core.exceptions import ValidationError

FEATURES = {
    "crm": "CRM tizimi",
    "reports": "Hisobotlar",
    "marketplace": "Marketplace'da e'lon berish",
    "mobile_app": "Mobil ilova",
    "notifications": "Email va SMS bildirishnomalar",
}


def validate_features(value):
    if not isinstance(value, dict):
        raise ValidationError("Imkoniyatlar {kalit: true/false} ko'rinishida bo'lishi kerak.")
    unknown = sorted(set(value) - set(FEATURES))
    if unknown:
        raise ValidationError(f"Noma'lum imkoniyat: {', '.join(unknown)}.")
    not_bool = sorted(key for key, flag in value.items() if not isinstance(flag, bool))
    if not_bool:
        raise ValidationError(
            f"Qiymat true yoki false bo'lishi kerak: {', '.join(not_bool)}."
        )
    