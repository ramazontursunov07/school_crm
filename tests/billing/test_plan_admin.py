from decimal import Decimal
from io import StringIO

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.billing.admin import PlanAdmin, PlanAdminForm
from apps.billing.features import FEATURES
from apps.billing.models import Plan

User = get_user_model()


def form_data(**overrides):
    data = {
        "name": "Start",
        "description": "",
        "audience": "any",
        "currency": "UZS",
        "price_monthly": "99000",
        "price_yearly": "",
        "max_branches": "",
        "max_staff": "",
        "max_students": "",
        "sort_order": "0",
        "is_active": "on",
        "is_public": "on",
    }
    data.update(overrides)
    return data


class PlanAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="Test-parol-12345"
        )
        self.client.force_login(self.admin_user)

    def test_changelist_and_add_pages_open(self):
        self.assertEqual(self.client.get(reverse("admin:billing_plan_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:billing_plan_add")).status_code, 200)

    def test_create_through_admin_saves_features_and_is_audited(self):
        response = self.client.post(
            reverse("admin:billing_plan_add"),
            form_data(code="start", feature_crm="on", feature_reports="on"),
        )

        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        plan = Plan.objects.get(code="start")
        self.assertEqual(plan.price_monthly, Decimal("99000"))
        self.assertEqual(
            plan.features,
            {key: key in ("crm", "reports") for key in FEATURES},
        )
        entry = AuditLog.objects.get(action="billing.plan_created")
        self.assertEqual(entry.actor, self.admin_user)
        self.assertEqual(entry.target_id, str(plan.pk))
        self.assertIsNone(entry.organization)

    def test_edit_through_admin_audits_changed_fields_and_keeps_code(self):
        plan = Plan.objects.create(code="start", name="Start", price_monthly=Decimal("99000"))
        url = reverse("admin:billing_plan_change", args=[plan.pk])

        response = self.client.post(
            url, form_data(code="hacked", price_monthly="120000", feature_crm="on")
        )

        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.code, "start")  # kod o'zgarmaydi
        self.assertEqual(plan.price_monthly, Decimal("120000"))
        entry = AuditLog.objects.get(action="billing.plan_updated")
        self.assertIn("price_monthly", entry.metadata["changed"])
        self.assertNotIn("code", entry.metadata["changed"])

    def test_invalid_admin_input_is_rejected(self):
        response = self.client.post(
            reverse("admin:billing_plan_add"),
            form_data(code="x", price_monthly="", price_yearly=""),
        )

        self.assertEqual(response.status_code, 200)  # forma xato bilan qaytadi
        self.assertFalse(Plan.objects.exists())

    def test_plans_cannot_be_deleted(self):
        plan = Plan.objects.create(code="start", name="Start", price_monthly=Decimal("1"))

        self.assertFalse(PlanAdmin(Plan, site).has_delete_permission(None))
        url = reverse("admin:billing_plan_delete", args=[plan.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(Plan.objects.filter(pk=plan.pk).exists())

    def test_form_shows_current_features(self):
        plan = Plan.objects.create(
            code="start", name="Start", price_monthly=Decimal("1"), features={"crm": True}
        )
        form = PlanAdminForm(instance=plan)

        self.assertTrue(form.fields["feature_crm"].initial)
        self.assertFalse(form.fields["feature_reports"].initial)


class SeedPlansTests(TestCase):
    def run_command(self):
        out = StringIO()
        call_command("seed_plans", stdout=out)
        return out.getvalue()

    def test_creates_starter_plans(self):
        output = self.run_command()

        self.assertEqual(
            list(Plan.objects.values_list("code", flat=True)), ["start", "standard", "pro"]
        )
        self.assertIn("yaratildi", output)
        self.assertIn("namuna", output)

    def test_is_idempotent_and_does_not_overwrite_edits(self):
        self.run_command()
        Plan.objects.filter(code="start").update(price_monthly=Decimal("123000"))

        output = self.run_command()

        self.assertEqual(Plan.objects.count(), 3)
        self.assertEqual(Plan.objects.get(code="start").price_monthly, Decimal("123000"))
        self.assertIn("o'zgartirilmadi", output)

    def test_starter_plans_are_valid_and_get_progressively_bigger(self):
        self.run_command()
        start, standard, pro = Plan.objects.all()

        for plan in (start, standard, pro):
            plan.full_clean()
        self.assertLess(start.price_monthly, standard.price_monthly)
        self.assertLess(standard.price_monthly, pro.price_monthly)
        self.assertLess(start.max_students, standard.max_students)
        self.assertIsNone(pro.max_students)
        self.assertTrue(pro.has_feature("marketplace"))
        self.assertFalse(start.has_feature("marketplace"))
