from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField("email", unique=True, null=True, blank=True)
    phone = models.CharField(
        "telefon", max_length=20, unique=True, null=True, blank=True
    )

    # Kod orqali tasdiqlangan paytlar. Kontakt o'zgarsa, belgi bekor bo'ladi.
    email_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    phone_verified_at = models.DateTimeField(null=True, blank=True, editable=False)

    @property
    def verified_email(self):
        return self.email if self.email and self.email_verified_at else None

    @property
    def verified_phone(self):
        return self.phone if self.phone and self.phone_verified_at else None

    @property
    def is_email_verified(self):
        return self.verified_email is not None

    @property
    def is_phone_verified(self):
        return self.verified_phone is not None

    def clean(self):
        super().clean()
        self._normalize_contacts()

    def save(self, *args, **kwargs):
        self._normalize_contacts()
        self._reset_verification_if_contact_changed(kwargs)
        super().save(*args, **kwargs)

    def _reset_verification_if_contact_changed(self, save_kwargs):
        update_fields = save_kwargs.get("update_fields")
        if self.pk is None or self._state.adding:
            return
        if update_fields is not None and not {"email", "phone"} & set(update_fields):
            return  # last_login yangilash kabi holatlarda qo'shimcha so'rov yo'q
        old = User.objects.filter(pk=self.pk).values("email", "phone").first()
        if old is None:
            return
        reset = []
        if old["email"] != self.email:
            self.email_verified_at = None
            reset.append("email_verified_at")
        if old["phone"] != self.phone:
            self.phone_verified_at = None
            reset.append("phone_verified_at")
        if reset and update_fields is not None:
            save_kwargs["update_fields"] = set(update_fields) | set(reset)

    def _normalize_contacts(self):
        # Bo'sh qiymat NULL bo'ladi, aks holda unique xato beradi
        self.email = (self.email or "").strip().lower() or None
        self.phone = (self.phone or "").strip() or None


class VerificationCode(models.Model):
    """Bir martalik kod: email/telefonni tasdiqlash va parolni tiklash.

    Kodning o'zi saqlanmaydi, faqat HMAC xeshi (6 xonali kodni oddiy xesh
    bo'yicha tez topish mumkin). Kod 10 daqiqa yashaydi va 5 marta xato
    kiritilsa yaroqsiz bo'ladi.
    """

    class Purpose(models.TextChoices):
        VERIFY_EMAIL = "verify_email", "Email tasdiqlash"
        VERIFY_PHONE = "verify_phone", "Telefon tasdiqlash"
        PASSWORD_RESET = "password_reset", "Parolni tiklash"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_codes",
    )
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    # Kod yuborilgan email yoki telefon (keyin kontakt o'zgarsa, kod eskiradi)
    target = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=64, editable=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "purpose", "-created_at"],
                name="vcode_user_purpose_idx",
            ),
        ]

    def __str__(self):
        return f"{self.purpose} -> user #{self.user_id}"


class DeviceToken(models.Model):
    """Mobil ilova uchun kirish tokeni. Har bir qurilma alohida token oladi.

    Xom token bazada saqlanmaydi, faqat SHA-256 xeshi (token 256 bit
    tasodifiy, shuning uchun oddiy xesh yetarli). Token ishlatilmasa
    `expires_at` da tugaydi; ishlatilsa muddat uzayadi, lekin yaratilganiga
    `ABSOLUTE_LIFETIME` dan keyin baribir yaroqsiz bo'ladi.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    device_name = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_used_at", "-id"]
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="devtoken_user_revoked_idx"),
        ]

    def __str__(self):
        return f"{self.device_name or 'qurilma'} (user #{self.user_id})"
