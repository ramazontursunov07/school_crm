from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.billing.features import FEATURES
from apps.billing.models import Plan


def make_plan(**fields):
    fields.setdefault("code", "start")
    fields.setdefault("name", "Start")
    fields.setdefault("price_monthly", Decimal("100000"))
    return Plan.objects.create(**fields)


class PlanModelTests(TestCase):
    def test_defaults(self):
        plan = make_plan()

        self.assertEqual(plan.currency, "UZS")
        self.assertEqual(plan.audience, Plan.Audience.ANY)
        self.assertTrue(plan.is_active)
        self.assertTrue(plan.is_public)
        self.assertEqual(plan.features, {})
        self.assertEqual(plan.limits, {"branches": None, "staff": None, "students": None})

    def test_audience_values_match_organization_types(self):
        from apps.organizations.models import Organization

        for value in Organization.Type.values:
            self.assertIn(value, Plan.Audience.values)

    def test_code_is_unique(self):
        make_plan()
        with self.assertRaises(ValidationError):
            make_plan(name="Boshqa")

    def test_needs_at_least_one_price(self):
        with self.assertRaises(ValidationError):
            make_plan(price_monthly=None, price_yearly=None)

    def test_yearly_only_and_monthly_only_are_allowed(self):
        make_plan(code="monthly", price_monthly=Decimal("1000"), price_yearly=None)
        make_plan(code="yearly", price_monthly=None, price_yearly=Decimal("10000"))

    def test_free_plan_is_allowed(self):
        plan = make_plan(price_monthly=Decimal("0"))
        self.assertEqual(plan.price_monthly, 0)

    def test_negative_price_rejected(self):
        with self.assertRaises(ValidationError):
            make_plan(price_monthly=Decimal("-1"))
        with self.assertRaises(ValidationError):
            make_plan(code="b", price_monthly=Decimal("1"), price_yearly=Decimal("-5"))

    def test_database_also_rejects_bad_prices(self):
        # full_clean aylanib o'tilsa ham (masalan queryset.update) baza to'sadi
        plan = make_plan()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Plan.objects.filter(pk=plan.pk).update(price_monthly=Decimal("-1"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Plan.objects.filter(pk=plan.pk).update(price_monthly=None, price_yearly=None)

    def test_currency_must_be_three_capital_letters(self):
        for bad in ("uzs", "UZ", "UZSS", "U2S", ""):
            with self.assertRaises(ValidationError, msg=bad):
                make_plan(code=f"c-{len(bad)}-{bad}"[:40] or "c", currency=bad)

    def test_code_must_be_a_slug(self):
        with self.assertRaises(ValidationError):
            make_plan(code="bor lik")

    def test_limits_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            make_plan(max_branches=-1)

    def test_features_validation(self):
        with self.assertRaises(ValidationError):
            make_plan(features={"uchar_gilam": True})
        with self.assertRaises(ValidationError):
            make_plan(features={"crm": "yes"})
        with self.assertRaises(ValidationError):
            make_plan(features=["crm"])
        make_plan(features={"crm": True, "reports": False})

    def test_has_feature_and_feature_map(self):
        plan = make_plan(features={"crm": True})

        self.assertTrue(plan.has_feature("crm"))
        self.assertFalse(plan.has_feature("reports"))
        self.assertEqual(set(plan.feature_map()), set(FEATURES))
        self.assertEqual(plan.feature_map()["crm"], True)
        self.assertEqual(plan.feature_map()["reports"], False)
        with self.assertRaises(KeyError):
            plan.has_feature("uchar_gilam")

    def test_yearly_discount_percent(self):
        cases = [
            (Decimal("100000"), Decimal("1000000"), 16),  # 1 200 000 dan 16.67% -> 16
            (Decimal("100000"), Decimal("1200000"), 0),
            (Decimal("100000"), Decimal("1500000"), 0),  # yillik qimmatroq: chegirma yo'q
            (Decimal("100000"), None, 0),
            (None, Decimal("1000000"), 0),
            (Decimal("0"), Decimal("0"), 0),
        ]
        for monthly, yearly, expected in cases:
            plan = Plan(code="x", name="X", price_monthly=monthly, price_yearly=yearly)
            self.assertEqual(plan.yearly_discount_percent, expected, (monthly, yearly))

    def test_ordering_by_sort_order_then_id(self):
        second = make_plan(code="b", sort_order=2)
        first = make_plan(code="a", sort_order=1)
        third = make_plan(code="c", sort_order=2)

        self.assertEqual(list(Plan.objects.all()), [first, second, third])
        