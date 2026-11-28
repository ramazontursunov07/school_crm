from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .features import FEATURES, validate_features

PRICE_MAX_DIGITS = 14
money_field = dict(
    max_digits=PRICE_MAX_DIGITS,
    decimal_places=2,
    null=True,
    blank=True,
    validators=[MinValueValidator(Decimal("0"))],
)


class Plan(models.Model):
    """CRM tarifi. Tarif hech qachon o'chirilmaydi, faqat `is_active=False`
    qilinadi (keyinchalik obuna va hisob-fakturalar unga bog'lanadi).

    Narx o'zgartirilsa, mavjud obunachilarga ta'sir qilmasligi kerak: obuna va
    hisob-faktura narxni o'zi saqlaydi (4-bosqichning keyingi qadamlarida).
    """

    class Audience(models.TextChoices):
        ANY = "any", "Barcha turlar"
        # Qiymatlar Organization.Type bilan bir xil bo'lishi shart.
        LEARNING_CENTER = "learning_center", "O'quv markazi"
        PRIVATE_SCHOOL = "private_school", "Xususiy maktab"

    code = models.SlugField(
        "kod",
        max_length=40,
        unique=True,
        help_text="Barqaror identifikator (masalan: standard). Yaratilgandan keyin o'zgartirilmaydi.",
    )
    name = models.CharField("nomi", max_length=100)
    description = models.TextField("tavsif", blank=True)
    audience = models.CharField(
        "kimlar uchun", max_length=20, choices=Audience.choices, default=Audience.ANY
    )

    currency = models.CharField(
        "valyuta",
        max_length=3,
        default="UZS",
        validators=[
            RegexValidator(r"^[A-Z]{3}$", "Valyuta kodi 3 ta bosh harf bo'lishi kerak (masalan UZS).")
        ],
    )
    price_monthly = models.DecimalField("oylik narx", **money_field)
    price_yearly = models.DecimalField(
        "yillik narx", help_text="Bo'sh bo'lsa, tarif yillik sotilmaydi.", **money_field
    )

    # Cheklovlar. Bo'sh qiymat = cheksiz. Amalda cheklash 4-bosqichning
    # "obunani cheklash" qadamida yoqiladi.
    max_branches = models.PositiveIntegerField("filiallar soni", null=True, blank=True)
    max_staff = models.PositiveIntegerField("xodimlar soni", null=True, blank=True)
    max_students = models.PositiveIntegerField("o'quvchilar soni", null=True, blank=True)

    features = models.JSONField("imkoniyatlar", default=dict, blank=True, validators=[validate_features])

    is_active = models.BooleanField(
        "sotuvda", default=True, help_text="O'chirilsa, yangi obuna olib bo'lmaydi."
    )
    is_public = models.BooleanField(
        "ochiq ro'yxatda",
        default=True,
        help_text="O'chirilsa, tarif narxlar sahifasida ko'rinmaydi (alohida kelishuv uchun).",
    )
    sort_order = models.PositiveSmallIntegerField("tartib", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(price_monthly__isnull=False) | Q(price_yearly__isnull=False),
                name="plan_has_a_price",
            ),
            models.CheckConstraint(
                condition=(Q(price_monthly__isnull=True) | Q(price_monthly__gte=0))
                & (Q(price_yearly__isnull=True) | Q(price_yearly__gte=0)),
                name="plan_prices_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        super().clean()
        if self.price_monthly is None and self.price_yearly is None:
            raise ValidationError("Kamida bitta narx (oylik yoki yillik) kiritilishi kerak.")

    def save(self, *args, **kwargs):
        # Tarifni faqat admin yaratadi va kam o'zgaradi, shuning uchun har saqlashda
        # to'liq tekshiramiz (JSON maydonni bazaning o'zi tekshira olmaydi).
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def yearly_discount_percent(self):
        """Yillik to'lov 12 oylik narxdan necha foiz arzon (butun songa pastga
        yaxlitlanadi, shunda mijozga ortiqcha va'da berilmaydi)."""
        if not self.price_monthly or self.price_yearly is None:
            return 0
        full_price = self.price_monthly * 12
        if self.price_yearly >= full_price:
            return 0
        return int((full_price - self.price_yearly) * 100 / full_price)

    @property
    def limits(self):
        """None = cheksiz."""
        return {
            "branches": self.max_branches,
            "staff": self.max_staff,
            "students": self.max_students,
        }

    def has_feature(self, key):
        if key not in FEATURES:
            raise KeyError(f"Noma'lum imkoniyat: {key}")
        return bool(self.features.get(key))

    def feature_map(self):
        """Barcha ma'lum imkoniyatlar: tarifda yo'qlari False bo'ladi."""
        return {key: bool(self.features.get(key)) for key in FEATURES}
    