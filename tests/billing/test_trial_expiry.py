from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.billing.models import Subscription
from apps.billing.services import expire_due_trials
from apps.organizations.models import Organization
from tests.billing.test_trial_api import TrialTestCase


class ExpiryTests(TrialTestCase):
    def start_trial(self, org=None, owner=None):
        self.login(owner or self.owner)
        url = reverse("subscription-trial", args=[(org or self.org).id])
        self.assertEqual(self.client.post(url, {"plan": "standard"}).status_code, 201)

    def end_trial(self, sub, *, days_ago=1):
        now = timezone.now()
        Subscription.objects.filter(pk=sub.pk).update(
            trial_started_at=now - timedelta(days=days_ago + 14),
            trial_ends_at=now - timedelta(days=days_ago),
        )

    def test_finished_trial_is_reported_as_expired_without_any_background_job(self):
        self.start_trial()
        self.end_trial(Subscription.objects.get())

        self.login(self.owner)
        data = self.client.get(self.state_url).json()

        self.assertEqual(data["subscription"]["status"], "expired")
        self.assertEqual(data["subscription"]["days_left"], 0)
        self.assertFalse(data["trial_available"])
        # bazada hali `trialing`: hisobot faqat vaqt bo'yicha
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.TRIALING)

    def test_expire_due_trials_closes_only_finished_ones(self):
        other_owner = self.make_user("boshqa")
        other_org = self.make_org("Boshqa markaz", owner=other_owner)
        self.start_trial()
        self.start_trial(org=other_org, owner=other_owner)
        self.end_trial(Subscription.objects.get(organization=self.org))

        closed = expire_due_trials()

        self.assertEqual(closed, 1)
        self.assertEqual(
            Subscription.objects.get(organization=self.org).status, Subscription.Status.EXPIRED
        )
        self.assertEqual(
            Subscription.objects.get(organization=other_org).status, Subscription.Status.TRIALING
        )

    def test_expiry_is_audited_without_actor(self):
        self.start_trial()
        self.end_trial(Subscription.objects.get())

        expire_due_trials()

        entry = AuditLog.objects.get(action="billing.trial_expired")
        self.assertEqual(entry.organization, self.org)
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.metadata["plan"], "standard")

    def test_expire_is_idempotent(self):
        self.start_trial()
        self.end_trial(Subscription.objects.get())

        self.assertEqual(expire_due_trials(), 1)
        self.assertEqual(expire_due_trials(), 0)
        self.assertEqual(AuditLog.objects.filter(action="billing.trial_expired").count(), 1)

    def test_running_trial_is_left_alone(self):
        self.start_trial()

        self.assertEqual(expire_due_trials(), 0)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.TRIALING)

    def test_command_reports_count(self):
        self.start_trial()
        self.end_trial(Subscription.objects.get())
        out = StringIO()

        call_command("expire_trials", stdout=out)

        self.assertIn("Yopilgan sinovlar: 1", out.getvalue())
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.EXPIRED)

    def test_expired_organization_can_still_view_its_state(self):
        self.start_trial()
        self.end_trial(Subscription.objects.get())
        expire_due_trials()
        Organization.objects.filter(pk=self.org.pk).update(is_active=False)

        self.login(self.owner)

        self.assertEqual(self.client.get(self.state_url).status_code, 200)
        