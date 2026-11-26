from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField("email", unique=True, null=True, blank=True)
    phone = models.CharField(
        "telefon", max_length=20, unique=True, null=True, blank=True
    )

    def clean(self):
        super().clean()
        self._normalize_contacts()

    def save(self, *args, **kwargs):
        self._normalize_contacts()
        super().save(*args, **kwargs)

    def _normalize_contacts(self):
        # Bo'sh qiymat NULL bo'ladi, aks holda unique xato beradi
        self.email = (self.email or "").strip().lower() or None
        self.phone = (self.phone or "").strip() or None
