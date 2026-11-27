"""Mobil ilova tokenlari: yaratish, tekshirish, bekor qilish."""

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import DeviceToken, User

IDLE_LIFETIME = timedelta(days=30)  # ishlatilmasa shuncha turadi
ABSOLUTE_LIFETIME = timedelta(days=180)  # ishlatilsa ham shundan keyin tugaydi
TOUCH_INTERVAL = timedelta(minutes=5)  # last_used_at'ni tez-tez yozmaslik uchun
MAX_DEVICES = 10


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


def active_tokens(user):
    now = timezone.now()
    return DeviceToken.objects.filter(
        user=user,
        revoked_at__isnull=True,
        expires_at__gt=now,
        created_at__gt=now - ABSOLUTE_LIFETIME,
    )


@transaction.atomic
def issue_token(*, user, device_name="", ip_address=None):
    """Yangi token yaratadi. (token_obyekti, xom_token) qaytaradi.

    Qurilmalar soni `MAX_DEVICES` dan oshsa, eng eski token bekor qilinadi."""
    # Parallel so'rovlar limitni chetlab o'tmasligi uchun qator qulflanadi
    User.objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    current = list(active_tokens(user).order_by("last_used_at", "id"))
    overflow = len(current) - (MAX_DEVICES - 1)
    if overflow > 0:
        DeviceToken.objects.filter(pk__in=[t.pk for t in current[:overflow]]).update(
            revoked_at=now
        )
    raw_token = secrets.token_urlsafe(32)
    token = DeviceToken.objects.create(
        user=user,
        token_hash=hash_token(raw_token),
        device_name=device_name.strip()[:100],
        ip_address=ip_address,
        last_used_at=now,
        expires_at=now + IDLE_LIFETIME,
    )
    return token, raw_token


def find_token(raw_token):
    """Yaroqli tokenni (user bilan) qaytaradi, bo'lmasa None."""
    now = timezone.now()
    token = (
        DeviceToken.objects.select_related("user")
        .filter(
            token_hash=hash_token(raw_token),
            revoked_at__isnull=True,
            expires_at__gt=now,
            created_at__gt=now - ABSOLUTE_LIFETIME,
        )
        .first()
    )
    if token is None or not token.user.is_active:
        return None
    return token


def touch_token(token):
    now = timezone.now()
    if now - token.last_used_at < TOUCH_INTERVAL:
        return
    new_expiry = min(now + IDLE_LIFETIME, token.created_at + ABSOLUTE_LIFETIME)
    DeviceToken.objects.filter(pk=token.pk).update(
        last_used_at=now, expires_at=new_expiry
    )


def revoke_token(token):
    DeviceToken.objects.filter(pk=token.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def revoke_all_tokens(user, *, except_token=None):
    """Foydalanuvchining barcha tokenlarini bekor qiladi. Bekor qilinganlar soni."""
    queryset = DeviceToken.objects.filter(user=user, revoked_at__isnull=True)
    if except_token is not None:
        queryset = queryset.exclude(pk=except_token.pk)
    return queryset.update(revoked_at=timezone.now())
