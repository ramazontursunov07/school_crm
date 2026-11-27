from django.conf import settings
from django.db import models
from django.db.models import F, Q


class FamilyInvite(models.Model):
    """Bog'lash uchun bir martalik kod. Uni bir tomon yaratadi (rozilik),
    ikkinchi tomon kiritadi (tasdiq). Ikkalasi bo'lmasa bog'lanish yaratilmaydi.

    Kod bazada saqlanmaydi, faqat HMAC xeshi."""

    class Role(models.TextChoices):
        PARENT = "parent", "Ota-ona"
        CHILD = "child", "Farzand"

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="family_invites",
    )
    # Kodni yaratgan kishi bog'lanishda kim bo'ladi
    creator_role = models.CharField(max_length=10, choices=Role.choices)
    code_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.creator_role} invite (user #{self.creator_id})"


class ParentChildLink(models.Model):
    """Ota-ona va farzand akkauntlari orasidagi tasdiqlangan bog'lanish.

    O'chirilmaydi: bekor qilinganda `revoked_at` to'ldiriladi (tarix saqlanadi)."""

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="child_links",
    )
    child = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(parent=F("child")),
                name="family_link_not_self",
            ),
            models.UniqueConstraint(
                fields=["parent", "child"],
                condition=Q(revoked_at__isnull=True),
                name="unique_active_family_link",
            ),
        ]

    def __str__(self):
        return f"parent #{self.parent_id} -> child #{self.child_id}"
    