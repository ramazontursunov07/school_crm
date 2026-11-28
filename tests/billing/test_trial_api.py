from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.billing.models import Plan, Subscription
from apps.organizations.models import Organization
from apps.organizations.roles import Role
from tests.organizations.helpers import TenantTestCase


class TrialTestCase(TenantTestCase):
    def setUp(self):
        self.owner = self.make_user("egasi")
        self.org = self.make_org("Markaz", owner=self.owner)
        self.plan = Plan.objects.create(
            code="standard",
            name="Standart",
            price_monthly=Decimal("249000"),
            max_branches=3,
            features={"crm": True},
        )
        self.state_url = reverse("subscription-detail", args=[self.org.id])
        self.trial_url = reverse("subscription-trial", args=[self.org.id])

    def start(self, plan="standard", url=None):
        return self.client.post(url or self.trial_url, {"plan": plan})

    def member(self, username, role):
        user = self.make_user(username)
        self.join(user, self.org, role)
        return user


class StartTrialTests(TrialTestCase):
    def test_owner_starts_trial(self):
        self.login(self.owner)

        response = self.start()

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "trialing")
        self.assertTrue(data["is_trial"])
        self.assertEqual(data["days_left"], 14)
        self.assertEqual(data["plan"]["code"], "standard")
        self.assertEqual(data["plan"]["limits"]["branches"], 3)

        sub = Subscription.objects.get()
        self.assertEqual(sub.organization, self.org)
        self.assertEqual(sub.trial_started_by, self.owner)
        self.assertEqual(sub.trial_ends_at - sub.trial_started_at, timedelta(days=14))

    def test_trial_length_follows_the_plan(self):
        Plan.objects.create(
            code="short", name="Short", price_monthly=Decimal("1"), trial_days=7
        )
        self.login(self.owner)

        response = self.start("short")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["days_left"], 7)
        sub = Subscription.objects.get()
        self.assertEqual(sub.trial_ends_at - sub.trial_started_at, timedelta(days=7))

    def test_client_cannot_choose_dates_or_status(self):
        self.login(self.owner)
        far = (timezone.now() + timedelta(days=3650)).isoformat()

        response = self.client.post(
            self.trial_url,
            {"plan": "standard", "trial_ends_at": far, "status": "expired", "trial_days": 9999},
        )

        self.assertEqual(response.status_code, 201)
        sub = Subscription.objects.get()
        self.assertEqual(sub.trial_ends_at - sub.trial_started_at, timedelta(days=14))
        self.assertEqual(sub.status, Subscription.Status.TRIALING)

    def test_start_is_audited_in_the_organization_history(self):
        self.login(self.owner)
        self.start()

        entry = AuditLog.objects.get(action="billing.trial_started")
        self.assertEqual(entry.organization, self.org)
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.metadata["plan"], "standard")
        self.assertEqual(entry.metadata["trial_days"], 14)

    def test_cannot_start_twice(self):
        self.login(self.owner)
        self.start()

        response = self.start()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.error_code(response), "trial_active")
        self.assertEqual(Subscription.objects.count(), 1)

    def test_cannot_restart_after_the_trial_ended(self):
        self.login(self.owner)
        self.start()
        now = timezone.now()
        Subscription.objects.update(
            trial_started_at=now - timedelta(days=15), trial_ends_at=now - timedelta(days=1)
        )

        response = self.start()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.error_code(response), "trial_already_used")
        self.assertEqual(Subscription.objects.count(), 1)

    def test_cannot_restart_after_expiry_was_recorded(self):
        self.login(self.owner)
        self.start()
        now = timezone.now()
        Subscription.objects.update(
            status=Subscription.Status.EXPIRED,
            trial_started_at=now - timedelta(days=15),
            trial_ends_at=now - timedelta(days=1),
        )

        self.assertEqual(self.start().status_code, 409)

    def test_bad_plans_are_rejected(self):
        Plan.objects.create(code="old", name="Old", price_monthly=Decimal("1"), is_active=False)
        Plan.objects.create(code="deal", name="Deal", price_monthly=Decimal("1"), is_public=False)
        Plan.objects.create(code="notrial", name="NoTrial", price_monthly=Decimal("1"), trial_days=0)
        self.login(self.owner)

        for code in ("yoq", "old", "deal", "notrial"):
            response = self.start(code)
            self.assertEqual(response.status_code, 400, code)
            self.assertIn("plan", response.json()["error"]["details"], code)
        self.assertFalse(Subscription.objects.exists())

    def test_plan_is_required_and_must_look_like_a_code(self):
        self.login(self.owner)

        self.assertEqual(self.client.post(self.trial_url, {}).status_code, 400)
        self.assertEqual(self.start("bor lik!").status_code, 400)

    def test_plan_for_another_organization_type_is_rejected(self):
        Plan.objects.create(
            code="school", name="School", price_monthly=Decimal("1"),
            audience=Plan.Audience.PRIVATE_SCHOOL,
        )
        Plan.objects.create(
            code="center", name="Center", price_monthly=Decimal("1"),
            audience=Plan.Audience.LEARNING_CENTER,
        )
        self.login(self.owner)

        self.assertEqual(self.start("school").status_code, 400)
        self.assertEqual(self.start("center").status_code, 201)

    def test_inactive_organization_cannot_start_trial(self):
        Organization.objects.filter(pk=self.org.pk).update(is_active=False)
        self.login(self.owner)

        self.assertEqual(self.start().status_code, 403)
        self.assertFalse(Subscription.objects.exists())

    def test_database_conflict_is_reported_as_conflict(self):
        self.login(self.owner)

        with mock.patch.object(Subscription.objects, "create", side_effect=IntegrityError):
            response = self.start()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.error_code(response), "trial_already_used")
        self.assertFalse(Subscription.objects.exists())


class UserTrialLimitTests(TrialTestCase):
    def test_one_user_cannot_farm_trials_with_many_organizations(self):
        orgs = [self.org] + [self.make_org(f"Markaz {i}", owner=self.owner) for i in range(2)]
        self.login(self.owner)

        with mock.patch("apps.billing.services.MAX_TRIALS_PER_USER", 2):
            codes = [
                self.start(url=reverse("subscription-trial", args=[org.id])).status_code
                for org in orgs
            ]
            blocked = self.start(url=reverse("subscription-trial", args=[orgs[2].id]))

        self.assertEqual(codes, [201, 201, 409])
        self.assertEqual(self.error_code(blocked), "trial_limit_reached")

    def test_limit_is_per_user(self):
        other = self.make_user("boshqa")
        other_org = self.make_org("Boshqa markaz", owner=other)

        with mock.patch("apps.billing.services.MAX_TRIALS_PER_USER", 1):
            self.login(self.owner)
            self.assertEqual(self.start().status_code, 201)
            self.login(other)
            response = self.start(url=reverse("subscription-trial", args=[other_org.id]))

        self.assertEqual(response.status_code, 201)

    def test_default_limit_is_three(self):
        from apps.billing import services

        self.assertEqual(services.MAX_TRIALS_PER_USER, 3)


class StateTests(TrialTestCase):
    def test_before_and_after_starting(self):
        self.login(self.owner)

        before = self.client.get(self.state_url).json()
        self.assertIsNone(before["subscription"])
        self.assertTrue(before["trial_available"])

        self.start()
        after = self.client.get(self.state_url).json()
        self.assertEqual(after["subscription"]["status"], "trialing")
        self.assertEqual(after["subscription"]["plan"]["code"], "standard")
        self.assertFalse(after["trial_available"])

    def test_trial_not_available_to_a_user_who_used_up_the_limit(self):
        with mock.patch("apps.billing.services.MAX_TRIALS_PER_USER", 0):
            self.login(self.owner)
            state = self.client.get(self.state_url).json()

        self.assertFalse(state["trial_available"])


class AccessTests(TrialTestCase):
    def test_who_can_start_a_trial(self):
        for role in (Role.DIRECTOR, Role.ADMIN, Role.ACCOUNTANT, Role.TEACHER):
            self.login(self.member(f"u-{role}", role))
            self.assertEqual(self.start().status_code, 403, role)
        self.assertFalse(Subscription.objects.exists())

    def test_who_can_see_the_subscription(self):
        expected = {
            Role.DIRECTOR: 200,
            Role.ACCOUNTANT: 200,
            Role.ADMIN: 403,
            Role.TEACHER: 403,
        }
        for role, code in expected.items():
            self.login(self.member(f"v-{role}", role))
            self.assertEqual(self.client.get(self.state_url).status_code, code, role)

    def test_non_member_sees_nothing_and_cannot_start(self):
        self.login(self.make_user("begona"))

        self.assertEqual(self.client.get(self.state_url).status_code, 404)
        self.assertEqual(self.start().status_code, 404)
        self.assertFalse(Subscription.objects.exists())

    def test_anonymous_is_rejected(self):
        client = APIClient()

        self.assertEqual(client.get(self.state_url).status_code, 403)
        self.assertEqual(client.post(self.trial_url, {"plan": "standard"}).status_code, 403)

    def test_organizations_are_isolated(self):
        other_owner = self.make_user("boshqa")
        other_org = self.make_org("Boshqa markaz", owner=other_owner)
        self.login(self.owner)
        self.start()

        self.login(other_owner)
        # o'z tashkiloti uchun sinov hali mavjud, begona tashkilot obunasini ko'rmaydi
        own = self.client.get(reverse("subscription-detail", args=[other_org.id])).json()
        self.assertIsNone(own["subscription"])
        self.assertTrue(own["trial_available"])
        self.assertEqual(self.client.get(self.state_url).status_code, 404)

    def test_removed_member_loses_access(self):
        director = self.member("direktor", Role.DIRECTOR)
        self.login(director)
        self.assertEqual(self.client.get(self.state_url).status_code, 200)
        director.memberships.update(is_active=False)

        self.assertEqual(self.client.get(self.state_url).status_code, 404)
        