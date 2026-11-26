from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import log_action

from . import roles
from .models import Branch, Invitation, Membership, Organization, hash_token
from .roles import Role

User = get_user_model()

INVITATION_LIFETIME = timedelta(days=7)
DEFAULT_BRANCH_NAME = "Asosiy filial"
INVALID_INVITATION = "Taklif topilmadi yoki yaroqsiz."


@transaction.atomic
def create_organization(*, user, name, type, country="UZ", request=None):
    organization = Organization.objects.create(name=name, type=type, country=country)
    Branch.objects.create(organization=organization, name=DEFAULT_BRANCH_NAME)
    Membership.objects.create(user=user, organization=organization, role=Role.OWNER)
    log_action(
        action="organization.created",
        organization=organization,
        actor=user,
        target=organization,
        metadata={"type": type},
        request=request,
    )
    return organization


def _contact_q(email, phone):
    query = Q(pk__in=[])
    if email:
        query |= Q(email=email)
    if phone:
        query |= Q(phone=phone)
    return query


@transaction.atomic
def create_invitation(
    *, organization, inviter_membership, email, phone, role, branch, request=None
):
    if not roles.can_assign(inviter_membership.role, role):
        raise PermissionDenied("Bu rolni berishga ruxsat yo'q.")

    already_member = Membership.objects.filter(
        organization=organization,
        is_active=True,
        user__in=User.objects.filter(_contact_q(email, phone)),
    )
    if already_member.exists():
        raise ValidationError({"detail": ["Bu odam allaqachon xodim."]})

    # Muddati o'tgan kutilayotgan takliflar qayta taklif qilishga to'sqinlik
    # qilmasligi uchun yopiladi.
    Invitation.objects.filter(
        organization=organization,
        status=Invitation.Status.PENDING,
        expires_at__lte=timezone.now(),
    ).filter(_contact_q(email, phone)).update(status=Invitation.Status.EXPIRED)

    if Invitation.objects.filter(
        organization=organization, status=Invitation.Status.PENDING
    ).filter(_contact_q(email, phone)).exists():
        raise ValidationError(
            {"detail": ["Bu odamga taklif allaqachon yuborilgan."]}
        )

    invitation, raw_token = Invitation.create_with_token(
        organization=organization,
        branch=branch,
        email=email,
        phone=phone,
        role=role,
        invited_by=inviter_membership.user,
        expires_at=timezone.now() + INVITATION_LIFETIME,
    )
    log_action(
        action="invitation.created",
        organization=organization,
        actor=inviter_membership.user,
        target=invitation,
        metadata={"role": role, "email": email, "phone": phone},
        request=request,
    )
    return invitation, raw_token


@transaction.atomic
def revoke_invitation(*, invitation, actor_membership, request=None):
    if not roles.can_assign(actor_membership.role, invitation.role):
        raise PermissionDenied("Bu taklifni bekor qilishga ruxsat yo'q.")
    if invitation.status != Invitation.Status.PENDING:
        raise ValidationError({"detail": ["Bu taklif allaqachon yopilgan."]})
    invitation.status = Invitation.Status.REVOKED
    invitation.save(update_fields=["status"])
    log_action(
        action="invitation.revoked",
        organization=invitation.organization,
        actor=actor_membership.user,
        target=invitation,
        request=request,
    )
    return invitation


@transaction.atomic
def accept_invitation(*, user, raw_token, request=None):
    invitation = (
        Invitation.objects.select_for_update(of=("self",))
        .select_related("organization", "branch")
        .filter(token_hash=hash_token(raw_token))
        .first()
    )
    if (
        invitation is None
        or invitation.status != Invitation.Status.PENDING
        or invitation.is_expired
        or not invitation.organization.is_active
    ):
        raise ValidationError({"token": [INVALID_INVITATION]})

    # DIQQAT: email/telefon tasdiqlash 3-bosqichda qo'shiladi. O'sha paytgacha
    # moslik tasdiqlanmagan qiymat bo'yicha tekshiriladi; 3-bosqichda bu
    # yerda faqat tasdiqlangan kontaktlar hisobga olinishi shart.
    matches = (
        invitation.email and user.email and invitation.email == user.email
    ) or (invitation.phone and user.phone and invitation.phone == user.phone)
    if not matches:
        raise ValidationError(
            {"token": ["Taklif sizning akkauntingizga mos kelmaydi."]}
        )

    branch = invitation.branch if invitation.branch and invitation.branch.is_active else None
    membership = (
        Membership.objects.select_for_update()
        .filter(user=user, organization=invitation.organization)
        .first()
    )
    if membership is not None and membership.is_active:
        raise ValidationError({"token": ["Siz allaqachon shu tashkilot xodimisiz."]})
    if membership is None:
        membership = Membership.objects.create(
            user=user,
            organization=invitation.organization,
            branch=branch,
            role=invitation.role,
        )
    else:
        membership.role = invitation.role
        membership.branch = branch
        membership.is_active = True
        membership.save()

    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_by = user
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_by", "accepted_at"])

    log_action(
        action="invitation.accepted",
        organization=invitation.organization,
        actor=user,
        target=invitation,
        metadata={"role": invitation.role},
        request=request,
    )
    return membership


@transaction.atomic
def update_membership(*, target, actor_membership, changes, request=None):
    """`changes`: role, branch, is_active kalitlaridan ba'zilari."""
    organization = target.organization
    if target.user_id == actor_membership.user_id:
        raise PermissionDenied("O'zingizning huquqlaringizni o'zgartira olmaysiz.")
    if not roles.can_assign(actor_membership.role, target.role):
        raise PermissionDenied("Bu xodimni boshqarishga ruxsat yo'q.")

    new_role = changes.get("role", target.role)
    if "role" in changes and not roles.can_assign(actor_membership.role, new_role):
        raise PermissionDenied("Bu rolni berishga ruxsat yo'q.")

    new_active = changes.get("is_active", target.is_active)
    loses_ownership = target.role == Role.OWNER and target.is_active and (
        new_role != Role.OWNER or not new_active
    )
    if loses_ownership:
        # Parallel so'rovlar oxirgi egani bir vaqtda olib tashlamasligi uchun
        # egalar qatorlari qulflanadi.
        active_owners = list(
            Membership.objects.select_for_update()
            .filter(organization=organization, role=Role.OWNER, is_active=True)
            .values_list("pk", flat=True)
        )
        if len(active_owners) <= 1:
            raise ValidationError(
                {"detail": ["Tashkilotda kamida bitta faol ega qolishi kerak."]}
            )

    before = {
        "role": target.role,
        "branch": target.branch_id,
        "is_active": target.is_active,
    }
    target.role = new_role
    target.is_active = new_active
    if "branch" in changes:
        target.branch = changes["branch"]
    target.save()
    after = {
        "role": target.role,
        "branch": target.branch_id,
        "is_active": target.is_active,
    }
    diff = {
        key: {"old": before[key], "new": after[key]}
        for key in before
        if before[key] != after[key]
    }
    if diff:
        log_action(
            action="membership.updated",
            organization=organization,
            actor=actor_membership.user,
            target=target,
            metadata={"user_id": target.user_id, "changes": diff},
            request=request,
        )
    return target
