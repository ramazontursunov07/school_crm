from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.billing.models import Plan
from apps.billing.serializers import PlanSerializer


def make_plan(**fields):
    fields.setdefault("code", "start")
    fields.setdefault("name", "Start")
    fields.setdefault("price_monthly", Decimal("1"))
    return Plan.objects.create(**fields)


class TrialDaysFieldTests(TestCase):
    def test_default_is_fourteen_days(self):
        self.assertEqual(make_plan().trial_days, 14)

    def test_zero_means_no_trial(self):
        self.assertEqual(make_plan(trial_days=0).trial_days, 0)

    def test_too_long_trial_rejected(self):
        with self.assertRaises(ValidationError):
            make_plan(trial_days=366)
        make_plan(trial_days=365)

    def test_api_exposes_trial_days(self):
        plan = make_plan(trial_days=7)

        self.assertEqual(PlanSerializer(plan).data["trial_days"], 7)
        