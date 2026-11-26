import math
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import VerificationCode
from .validators import normalize_phone

User = get_user_model()


def authenticate_by_identifier(request, identifier, password):
    """Login, email yoki telefon bo'yicha tekshiradi."""
    identifier = identifier.strip()
    if "@" in identifier:
        users = User.objects.filter(email__iexact=identifier)
    elif identifier.startswith("+"):
        users = User.objects.filter(phone=normalize_phone(identifier) or identifier)
    else:
        users = None

    if users is None:
        username = identifier
    else:
        user = users.first()
        # Topilmasa ham authenticate chaqiriladi: javob vaqti orqali akkaunt
        # bor-yo'qligini bilish qiyinlashadi
        username = user.get_username() if user else ""

    return authenticate(request, username=username, password=password)


# --- Tasdiqlash kodlari -------------------------------------------------

CODE_LIFETIME = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CODES_PER_HOUR = 5


class CodeRateLimited(Exception):
    """Kod juda tez-tez so'ralmoqda. `wait` — kutish soniyalari."""

    def __init__(self, wait):
        super().__init__(wait)
        self.wait = wait


def _hash_code(*, user, purpose, target, code):
    return salted_hmac(
        "accounts.verification-code",
        f"{user.pk}:{purpose}:{target}:{code}",
        algorithm="sha256",
    ).hexdigest()


@transaction.atomic
def issue_code(*, user, purpose, target):
    """Yangi kod yaratadi va uni (xom holda) qaytaradi. Eski kodlar yaroqsiz
    bo'ladi. Bir foydalanuvchiga 60 soniyada 1 ta va soatiga 5 tagacha kod."""
    # Parallel so'rovlar cheklovni chetlab o'tmasligi uchun qator qulflanadi
    User.objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    recent = VerificationCode.objects.filter(
        user=user, purpose=purpose, created_at__gt=now - timedelta(hours=1)
    )
    latest = recent.first()
    if latest is not None and now - latest.created_at < RESEND_COOLDOWN:
        wait = RESEND_COOLDOWN - (now - latest.created_at)
        raise CodeRateLimited(math.ceil(wait.total_seconds()))
    if recent.count() >= MAX_CODES_PER_HOUR:
        oldest = recent.last()
        wait = oldest.created_at + timedelta(hours=1) - now
        raise CodeRateLimited(max(1, math.ceil(wait.total_seconds())))

    VerificationCode.objects.filter(
        user=user, purpose=purpose, used_at__isnull=True
    ).update(used_at=now)
    code = f"{secrets.randbelow(10**6):06d}"
    VerificationCode.objects.create(
        user=user,
        purpose=purpose,
        target=target,
        code_hash=_hash_code(user=user, purpose=purpose, target=target, code=code),
        expires_at=now + CODE_LIFETIME,
    )
    return code


@transaction.atomic
def check_code(*, user, purpose, target, code):
    """Kod to'g'rimi? To'g'ri bo'lsa kod ishlatilgan deb belgilanadi.
    Xato urinish hisoblanadi; 5 xatodan keyin kod yaroqsiz.

    Xatoda istisno ko'tarilmaydi (urinish hisobi saqlanib qolishi uchun)."""
    now = timezone.now()
    verification = (
        VerificationCode.objects.select_for_update()
        .filter(
            user=user,
            purpose=purpose,
            target=target,
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .first()
    )
    if verification is None or verification.attempts >= MAX_ATTEMPTS:
        return False
    verification.attempts += 1
    expected = _hash_code(
        user=user, purpose=purpose, target=target, code=str(code).strip()
    )
    ok = constant_time_compare(verification.code_hash, expected)
    if ok:
        verification.used_at = now
    verification.save(update_fields=["attempts", "used_at"])
    return ok


def mark_verified(user, channel):
    field = "email_verified_at" if channel == "email" else "phone_verified_at"
    setattr(user, field, timezone.now())
    user.save(update_fields=[field])


def resolve_reset_target(identifier):
    """Parolni tiklash kodi qayerga yuboriladi: (user, target) yoki None.

    Faqat TASDIQLANGAN email/telefonga yuboriladi. Aks holda boshqa odamning
    emailini kiritib ro'yxatdan o'tgan kishi, email egasi akkauntni tiklab
    olishiga yo'l qo'yilgan bo'lardi."""
    identifier = identifier.strip()
    if "@" in identifier:
        user = User.objects.filter(email__iexact=identifier).first()
        target = user.verified_email if user else None
    elif identifier.startswith("+"):
        phone = normalize_phone(identifier) or identifier
        user = User.objects.filter(phone=phone).first()
        target = user.verified_phone if user else None
    else:
        user = User.objects.filter(username__iexact=identifier).first()
        target = (user.verified_email or user.verified_phone) if user else None
    if user is None or not user.is_active or target is None:
        return None
    return user, target
