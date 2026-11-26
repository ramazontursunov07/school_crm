import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.text import slugify

from .roles import Role


def generate_unique_slug(name):
    base = slugify(name)[:60] or "org"
    slug = base
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


class Organization(models.Model):
    class Type(models.TextChoices):
        LEARNING_CENTER = "learning_center", "O'quv markazi"
        PRIVATE_SCHOOL = "private_school", "Xususiy maktab"

    name = models.CharField("nomi", max_length=200)
    slug = models.SlugField(max_length=80, unique=True, editable=False)
    type = models.CharField("turi", max_length=20, choices=Type.choices)
    # ISO 3166-1 alpha-2. 7-bosqichda baholash sozlamalari shunga bog'lanadi.
    country = models.CharField("davlat", max_length=2, default="UZ")
    is_active = models.BooleanField("faol", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(self.name)
        super().save(*args, **kwargs)


class Branch(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField("nomi", max_length=200)
    address = models.CharField("manzil", max_length=300, blank=True)
    phone = models.CharField("telefon", max_length=20, blank=True)
    is_active = models.BooleanField("faol", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "branches"
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "organization",
                name="unique_branch_name_per_organization",
            ),
        ]

    def __str__(self):
        return f"{self.organization} / {self.name}"


class Membership(models.Model):
    """Foydalanuvchining tashkilotdagi o'rni. Bir foydalanuvchi bir nechta
    tashkilotda, har birida o'z roli bilan ishlashi mumkin."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    # Bo'sh bo'lsa, xodim barcha filiallarda ishlaydi.
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField("faol", default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="unique_membership_per_user_and_organization",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"

    def clean(self):
        super().clean()
        if self.branch_id and self.branch.organization_id != self.organization_id:
            raise ValidationError({"branch": "Filial boshqa tashkilotga tegishli."})


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        ACCEPTED = "accepted", "Qabul qilingan"
        REVOKED = "revoked", "Bekor qilingan"
        EXPIRED = "expired", "Muddati o'tgan"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    # Xom token bazada saqlanmaydi, faqat uning xeshi.
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(phone__isnull=False),
                name="invitation_has_email_or_phone",
            ),
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=Q(status="pending", email__isnull=False),
                name="unique_pending_invitation_email",
            ),
            models.UniqueConstraint(
                fields=["organization", "phone"],
                condition=Q(status="pending", phone__isnull=False),
                name="unique_pending_invitation_phone",
            ),
        ]

    def __str__(self):
        return f"{self.email or self.phone} -> {self.organization} ({self.role})"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def effective_status(self):
        if self.status == self.Status.PENDING and self.is_expired:
            return self.Status.EXPIRED
        return self.status

    @classmethod
    def create_with_token(cls, **fields):
        raw_token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(token_hash=hash_token(raw_token), **fields)
        return invitation, raw_token
    