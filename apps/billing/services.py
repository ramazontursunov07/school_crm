"""Sinov davri qoidalari.

- Tashkilot sinovdan umri davomida bir marta foydalanadi (bazada ham cheklangan).
- Bitta foydalanuvchi cheklangan miqdorda sinov boshlay oladi: ko'p tashkilot
  ochib, sinovni qayta-qayta olishga qarshi.
- Sinov muddati serverda hisoblanadi: tarifdagi `trial_days` bo'yicha.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.audit.services import log_action
from apps.organizations.models import Organization

from .models import Plan, Subscription

MAX_TRIALS_PER_USER = 3


class TrialConflict(APIException):
    """Sinovni hozir boshlab bo'lmaydi (holat to'qnashuvi). Kod xatoning turini bildiradi."""

    status_code = 409

    def __init__(self, code, detail):
        super().__init__(detail=detail, code=code)


def current_subscription(organization):
    return organization.subscriptions.select_related("plan").first()


def _trials_started_by(user):
    return Subscription.objects.filter(
        trial_started_by=user, trial_started_at__isnull=False
    ).count()


def trial_available(organization, user):
    """Foydalanuvchi shu tashkilot uchun sinov boshlay oladimi (tarif tanlashdan oldingi holat)."""
    return (
        not organization.subscriptions.exists()
        and _trials_started_by(user) < MAX_TRIALS_PER_USER
    )


def _trial_plan(organization, code):
    plan = Plan.objects.filter(code=code, is_active=True, is_public=True).first()
    if plan is None:
        raise ValidationError({"plan": ["Tarif topilmadi."]})
    if plan.trial_days <= 0:
        raise ValidationError({"plan": ["Bu tarif uchun sinov muddati yo'q."]})
    if plan.audience not in (Plan.Audience.ANY, organization.type):
        raise ValidationError({"plan": ["Bu tarif sizning tashkilot turiga mos emas."]})
    return plan


def start_trial(*, organization, plan_code, user, request=None):
    plan = _trial_plan(organization, plan_code)
    now = timezone.now()
    try:
        with transaction.atomic():
            # Tashkilot qatorini qulflash: parallel so'rovlar ikkita sinov ochmasin.
            Organization.objects.select_for_update().get(pk=organization.pk)

            existing = current_subscription(organization)
            if existing is not None:
                if existing.is_usable(now):
                    raise TrialConflict(
                        "trial_active", "Tashkilotda sinov muddati allaqachon boshlangan."
                    )
                raise TrialConflict(
                    "trial_already_used",
                    "Bu tashkilot sinov muddatidan allaqachon foydalangan.",
                )
            if _trials_started_by(user) >= MAX_TRIALS_PER_USER:
                raise TrialConflict(
                    "trial_limit_reached",
                    "Siz boshlashingiz mumkin bo'lgan sinovlar soni tugagan.",
                )

            subscription = Subscription.objects.create(
                organization=organization,
                plan=plan,
                status=Subscription.Status.TRIALING,
                trial_started_at=now,
                trial_ends_at=now + timedelta(days=plan.trial_days),
                trial_started_by=user,
            )
    except IntegrityError:
        # Baza cheklovi parallel so'rovni ushlab qoldi.
        raise TrialConflict(
            "trial_already_used", "Bu tashkilot sinov muddatidan allaqachon foydalangan."
        )

    log_action(
        action="billing.trial_started",
        organization=organization,
        actor=user,
        target=subscription,
        metadata={
            "plan": plan.code,
            "trial_days": plan.trial_days,
            "ends_at": subscription.trial_ends_at.isoformat(),
        },
        request=request,
    )
    return subscription


def expire_due_trials(now=None):
    """Muddati o'tgan sinovlarni `expired` qiladi. Nechtasi yopilganini qaytaradi.

    Muddatdan keyin sinov baribir ishlamaydi (`effective_status`); bu funksiya
    holatni bazada yangilaydi va tarixga yozadi. Vaqti-vaqti bilan ishga
    tushiriladi (`manage.py expire_trials`, 9-bosqichda jadvalga qo'yiladi).
    """
    now = now or timezone.now()
    closed = 0
    due_ids = list(
        Subscription.objects.filter(
            status=Subscription.Status.TRIALING, trial_ends_at__lte=now
        ).values_list("pk", flat=True)
    )
    for pk in due_ids:
        with transaction.atomic():
            subscription = (
                Subscription.objects.select_for_update()
                .select_related("plan")
                .get(pk=pk)
            )
            if subscription.status != Subscription.Status.TRIALING:
                continue  # boshqa jarayon allaqachon yopgan
            subscription.status = Subscription.Status.EXPIRED
            subscription.save(update_fields=["status", "updated_at"])
            log_action(
                action="billing.trial_expired",
                organization=subscription.organization,
                target=subscription,
                metadata={"plan": subscription.plan.code},
            )
            closed += 1
    return closed
