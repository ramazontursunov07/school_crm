"""Rollar va ruxsatlar.

Ruxsatlar kodda saqlanadi (bazada emas): ularni o'zgartirish kod ko'rigidan
o'tadi va testlanadi. Tashkilotga xos rollar keyingi bosqichlarda
(ota-ona, o'quvchi) shu yerga qo'shiladi.
"""

from django.db import models


class Role(models.TextChoices):
    OWNER = "owner", "Egasi"
    DIRECTOR = "director", "Direktor"
    ADMIN = "admin", "Administrator"
    ACCOUNTANT = "accountant", "Hisobchi"
    TEACHER = "teacher", "O'qituvchi"


ROLE_RANK = {
    Role.OWNER: 50,
    Role.DIRECTOR: 40,
    Role.ADMIN: 30,
    Role.ACCOUNTANT: 20,
    Role.TEACHER: 10,
}

ORG_VIEW = "org.view"
ORG_MANAGE = "org.manage"
BRANCH_VIEW = "branch.view"
BRANCH_MANAGE = "branch.manage"
MEMBERS_VIEW = "members.view"
MEMBERS_INVITE = "members.invite"
MEMBERS_MANAGE = "members.manage"
AUDIT_VIEW = "audit.view"
BILLING_VIEW = "billing.view"
BILLING_MANAGE = "billing.manage"

_ALL = frozenset(
    {
        ORG_VIEW,
        ORG_MANAGE,
        BRANCH_VIEW,
        BRANCH_MANAGE,
        MEMBERS_VIEW,
        MEMBERS_INVITE,
        MEMBERS_MANAGE,
        AUDIT_VIEW,
        BILLING_VIEW,
        BILLING_MANAGE,
    }
)
_READ_ONLY = frozenset({ORG_VIEW, BRANCH_VIEW, MEMBERS_VIEW})

ROLE_PERMISSIONS = {
    Role.OWNER: _ALL,
    # Obuna va to'lov: boshqarish faqat egasida, ko'rish direktor va hisobchida ham.
    Role.DIRECTOR: _ALL - {ORG_MANAGE, BILLING_MANAGE},
    Role.ADMIN: _READ_ONLY | {BRANCH_MANAGE, MEMBERS_INVITE, MEMBERS_MANAGE},
    Role.ACCOUNTANT: _READ_ONLY | {BILLING_VIEW},
    Role.TEACHER: _READ_ONLY,
}


def has_permission(role, permission):
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def can_assign(actor_role, target_role):
    """Foydalanuvchi `target_role` rolini berishi / shu rolli odamni
    boshqarishi mumkinmi.

    Egasi hammani boshqaradi. Qolganlar faqat o'zidan pastroq rolni
    boshqaradi (o'zi bilan teng rolni ham emas).
    """
    if actor_role == Role.OWNER:
        return True
    actor_rank = ROLE_RANK.get(actor_role)
    target_rank = ROLE_RANK.get(target_role)
    if actor_rank is None or target_rank is None:
        return False
    return actor_rank > target_rank
