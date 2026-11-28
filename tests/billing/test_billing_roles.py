from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import Plan, Subscription
from apps.organizations.models import Organization


class SubscriptionBase(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(code="start", name="Start", price_monthly=Decimal("1"))
        self.org = Organization.objects.create(
            name="Markaz", type=Organization.Type.LEARNING_CENTER
        )

    def make(self, organization=None, **fields):
        now = timezone.now()
        fields.setdefault("trial_started_at", now)
        fields.setdefault("trial_ends_at", now + timedelta(days=14))
        return Subscription.objects.create(
            organization=organization or self.org, plan=self.plan, **fields
        )


class ConstraintTests(SubscriptionBase):
    def test_one_trial_per_organization_even_after_it_expired(self):
        self.make(status=Subscription.Status.EXPIRED)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(status=Subscription.Status.EXPIRED)

    def test_other_organizations_have_their_own_trial(self):
        other = Organization.objects.create(
            name="Maktab", type=Organization.Type.PRIVATE_SCHOOL
        )
        self.make()
        self.make(organization=other)

        self.assertEqual(Subscription.objects.count(), 2)

    def test_only_one_open_subscription_per_organization(self):
        self.make(trial_started_at=None, trial_ends_at=None)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(trial_started_at=None, trial_ends_at=None)

    def test_trial_dates_must_be_consistent(self):
        now = timezone.now()
        for started, ends in (
            (now, now),  # tugash boshlanishdan keyin bo'lishi shart
            (now, now - timedelta(days=1)),
            (now, None),  # faqat bittasi berilgan
            (None, now),
        ):
            with self.assertRaises(IntegrityError, msg=(started, ends)), transaction.atomic():
                self.make(trial_started_at=started, trial_ends_at=ends)

    def test_plan_with_subscriptions_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        self.make()
        with self.assertRaises(ProtectedError):
            self.plan.delete()


class StatusTests(SubscriptionBase):
    def sub(self, *, ends_in, status=Subscription.Status.TRIALING):
        now = timezone.now()
        return Subscription(
            organization=self.org,
            plan=self.plan,
            status=status,
            trial_started_at=now - timedelta(days=1),
            trial_ends_at=now + ends_in,
        )

    def test_active_trial(self):
        sub = self.sub(ends_in=timedelta(days=5))

        self.assertTrue(sub.is_trial)
        self.assertEqual(sub.effective_status(), Subscription.Status.TRIALING)
        self.assertTrue(sub.is_usable())

    def test_trial_ends_by_time_even_if_status_was_not_updated(self):
        sub = self.sub(ends_in=-timedelta(seconds=1))

        self.assertEqual(sub.status, Subscription.Status.TRIALING)
        self.assertEqual(sub.effective_status(), Subscription.Status.EXPIRED)
        self.assertFalse(sub.is_usable())
        self.assertEqual(sub.days_left(), 0)

    def test_trial_ends_exactly_at_deadline(self):
        now = timezone.now()
        sub = Subscription(
            organization=self.org, plan=self.plan,
            trial_started_at=now - timedelta(days=1), trial_ends_at=now,
        )

        self.assertFalse(sub.is_usable(now))

    def test_days_left_rounds_up_partial_days(self):
        self.assertEqual(self.sub(ends_in=timedelta(hours=1)).days_left(), 1)
        self.assertEqual(self.sub(ends_in=timedelta(days=13, hours=1)).days_left(), 14)
        self.assertEqual(self.sub(ends_in=timedelta(days=14)).days_left(), 14)

    def test_expired_status_stays_expired(self):
        sub = self.sub(ends_in=timedelta(days=5), status=Subscription.Status.EXPIRED)

        self.assertEqual(sub.effective_status(), Subscription.Status.EXPIRED)
        self.assertFalse(sub.is_usable())
        self.assertEqual(sub.days_left(), 0)
        