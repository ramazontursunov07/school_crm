from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Harakatlar tarixi. Yozuv faqat qo'shiladi, o'zgartirilmaydi."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "-created_at"], name="audit_org_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.action} #{self.pk}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Harakatlar tarixini o'zgartirib bo'lmaydi.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Harakatlar tarixini o'chirib bo'lmaydi.")
    