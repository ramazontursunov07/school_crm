from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.billing.admin import SubscriptionAdmin
from apps.billing.models import Plan, Subscription
from apps.organizations.models import Organization

User = get_user_model()


class SubscriptionAdminTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="Test-parol-12345"
        )
        self.client.force_login(self.boss)
        plan = Plan.objects.create(code="start", name="Start", price_monthly=Decimal("1"))
        org = Organization.objects.create(name="Markaz", type=Organization.Type.LEARNING_CENTER)
        now = timezone.now()
        self.sub = Subscription.objects.create(
            organization=org,
            plan=plan,
            trial_started_at=now - timedelta(days=15),
            trial_ends_at=now - timedelta(days=1),  # vaqti o'tgan, lekin hali `trialing`
        )

    def test_changelist_shows_time_based_state(self):
        response = self.client.get(reverse("admin:billing_subscription_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Muddati tugagan")

    def test_admin_is_read_only(self):
        admin_obj = SubscriptionAdmin(Subscription, site)

        self.assertFalse(admin_obj.has_add_permission(None))
        self.assertFalse(admin_obj.has_change_permission(None, self.sub))
        self.assertFalse(admin_obj.has_delete_permission(None, self.sub))
        self.assertEqual(self.client.get(reverse("admin:billing_subscription_add")).status_code, 403)
