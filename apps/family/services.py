import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import ValidationError

from .models import FamilyInvite, ParentChildLink

CODE_LIFETIME = timedelta(hours=24)
MAX_ACTIVE_INVITES = 5
# 0, O, 1, I, L yo'q: ovozda aytganda adashmaslik uchun
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8

INVALID_CODE = "Kod noto'g'ri yoki muddati o'tgan."


def normalize_code(value):
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def hash_code(code):
    return salted_hmac(
        "family.invite-code", normalize_code(code), algorithm="sha256"
    ).hexdigest()


def active_invites(user):
    return FamilyInvite.objects.filter(
        creator=user,
        used_at__isnull=True,
        cancelled_at__isnull=True,
        expires_at__gt=timezone.now(),
    )


def _require_verified_parent(user):
    if user.verified_email is None and user.verified_phone is None:
        raise ValidationError(
            {
                "detail": [
                    "Ota-ona akkaunti uchun email yoki telefon tasdiqlangan "
                    "bo'lishi kerak."
                ]
            }
        )


@transaction.atomic
def create_invite(*, user, role):
    """Yangi kod yaratadi. (invite, xom_kod) qaytaradi. Kod faqat shu yerda ko'rinadi."""
    if role == FamilyInvite.Role.PARENT:
        _require_verified_parent(user)
    # Parallel so'rovlar limitni chetlab o'tmasligi uchun qator qulflanadi
    type(user).objects.select_for_update().get(pk=user.pk)
    if active_invites(user).count() >= MAX_ACTIVE_INVITES:
        raise ValidationError(
            {"detail": ["Faol kodlar ko'p. Keraksizini bekor qiling yoki kuting."]}
        )
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    invite = FamilyInvite.objects.create(
        creator=user,
        creator_role=role,
        code_hash=hash_code(code),
        expires_at=timezone.now() + CODE_LIFETIME,
    )
    return invite, code


@transaction.atomic
def accept_invite(*, user, code):
    """Kodni qabul qilib, bog'lanishni yaratadi. Yaratilgan ParentChildLink qaytadi."""
    invite = (
        FamilyInvite.objects.select_for_update(of=("self",))
        .select_related("creator")
        .filter(code_hash=hash_code(code))
        .first()
    )
    if (
        invite is None
        or invite.used_at is not None
        or invite.cancelled_at is not None
        or invite.expires_at <= timezone.now()
        or not invite.creator.is_active
    ):
        raise ValidationError({"code": [INVALID_CODE]})
    if invite.creator_id == user.pk:
        raise ValidationError({"code": ["O'zingiz yaratgan kodni kiritib bo'lmaydi."]})

    if invite.creator_role == FamilyInvite.Role.PARENT:
        parent, child = invite.creator, user
    else:
        parent, child = user, invite.creator
    _require_verified_parent(parent)

    if ParentChildLink.objects.filter(
        revoked_at__isnull=True
    ).filter(
        Q(parent=parent, child=child) | Q(parent=child, child=parent)
    ).exists():
        raise ValidationError({"detail": ["Bu akkauntlar allaqachon bog'langan."]})

    link = ParentChildLink.objects.create(parent=parent, child=child)
    invite.used_at = timezone.now()
    invite.used_by = user
    invite.save(update_fields=["used_at", "used_by"])
    return link


def active_links(user):
    return ParentChildLink.objects.filter(
        Q(parent=user) | Q(child=user), revoked_at__isnull=True
    ).select_related("parent", "child")


def revoke_link(*, link, by):
    link.revoked_at = timezone.now()
    link.revoked_by = by
    link.save(update_fields=["revoked_at", "revoked_by"])


# --- Boshqa bosqichlar uchun: kim kimning ma'lumotini ko'ra oladi ---------


def is_parent_of(parent, child):
    """`parent` akkaunti `child` akkauntining faol ota-onasimi."""
    if not getattr(parent, "is_authenticated", False):
        return False
    return ParentChildLink.objects.filter(
        parent=parent, child=child, revoked_at__isnull=True
    ).exists()


def children_of(user):
    return ParentChildLink.objects.filter(
        parent=user, revoked_at__isnull=True
    ).values_list("child_id", flat=True)


def parents_of(user):
    return ParentChildLink.objects.filter(
        child=user, revoked_at__isnull=True
    ).values_list("parent_id", flat=True)
