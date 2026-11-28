from decimal import Decimal
from math import ceil

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

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

    trial_days = models.PositiveSmallIntegerField(
        "sinov muddati (kun)",
        default=14,
        validators=[MaxValueValidator(365)],
        help_text="Tashkilot bu tarifni necha kun bepul sinay oladi. 0 bo'lsa, sinov yo'q.",
    )

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


class Subscription(models.Model):
    """Tashkilotning tarifdagi holati. Hozircha faqat sinov davri; pullik
    obuna (oylik/yillik) keyingi qadamda shu modelga qo'shiladi.

    Sinov muddati serverda hisoblanadi va mijoz tomonidan o'zgartirilmaydi.
    Sinov tugaganini `effective_status()` vaqt bo'yicha o'zi aniqlaydi, shuning
    uchun `expire_trials` buyrug'i kechiksa ham sinov muddatidan keyin davom etmaydi.
    """

    class Status(models.TextChoices):
        TRIALING = "trialing", "Sinov davrida"
        EXPIRED = "expired", "Muddati tugagan"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIALING)

    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    # Foydalanuvchi o'chirilsa bo'sh qoladi (tashkilotdagi sinov hisobi saqlanadi).
    trial_started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # Har bir tashkilot sinovdan umri davomida faqat bir marta foydalanadi.
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(trial_ends_at__isnull=False),
                name="one_trial_per_organization",
            ),
            # Tashkilotda bir vaqtda bitta ochiq (sinov davridagi) obuna.
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(status="trialing"),
                name="one_open_subscription_per_organization",
            ),
            models.CheckConstraint(
                condition=Q(trial_started_at__isnull=True, trial_ends_at__isnull=True)
                | Q(
                    trial_started_at__isnull=False,
                    trial_ends_at__isnull=False,
                    trial_ends_at__gt=F("trial_started_at"),
                ),
                name="subscription_trial_dates_valid",
            ),
        ]

    def __str__(self):
        return f"{self.organization_id}: {self.plan_id} ({self.status})"

    @property
    def is_trial(self):
        return self.trial_ends_at is not None

    def effective_status(self, now=None):
        now = now or timezone.now()
        if (
            self.status == self.Status.TRIALING
            and self.trial_ends_at is not None
            and self.trial_ends_at <= now
        ):
            return self.Status.EXPIRED
        return self.status

    def is_usable(self, now=None):
        """Tashkilot hozir tarif imkoniyatlaridan foydalana oladimi."""
        return self.effective_status(now) == self.Status.TRIALING

    def days_left(self, now=None):
        """Sinovning qolgan kunlari (to'liq bo'lmagan kun ham 1 kun hisoblanadi)."""
        now = now or timezone.now()
        if not self.is_usable(now):
            return 0
        return max(0, ceil((self.trial_ends_at - now).total_seconds() / 86400))
    