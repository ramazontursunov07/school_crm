from decimal import Decimal

from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.billing.features import FEATURES
from apps.billing.models import Plan


class PlanApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.start = Plan.objects.create(
            code="start",
            name="Start",
            price_monthly=Decimal("99000"),
            price_yearly=Decimal("990000"),
            max_branches=1,
            max_staff=5,
            features={"crm": True},
            sort_order=1,
        )
        self.pro = Plan.objects.create(
            code="pro",
            name="Pro",
            price_monthly=Decimal("499000"),
            max_students=None,
            features={"crm": True, "reports": True},
            sort_order=2,
        )
        self.url = reverse("plan-list")

    def codes(self, response):
        return [plan["code"] for plan in response.json()]

    def test_list_is_public(self):
        response = APIClient().get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.codes(response), ["start", "pro"])

    def test_stale_credentials_do_not_break_public_list(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer eskirgan-token")

        self.assertEqual(client.get(self.url).status_code, 200)

    def test_plan_fields(self):
        data = self.client.get(self.url).json()[0]

        self.assertEqual(data["code"], "start")
        self.assertEqual(data["currency"], "UZS")
        self.assertEqual(data["price_monthly"], "99000.00")  # pul satr sifatida
        self.assertEqual(data["price_yearly"], "990000.00")
        self.assertEqual(data["yearly_discount_percent"], 16)
        self.assertEqual(
            data["limits"], {"branches": 1, "staff": 5, "students": None}
        )
        self.assertEqual(set(data["features"]), set(FEATURES))
        self.assertTrue(data["features"]["crm"])
        self.assertFalse(data["features"]["reports"])

    def test_monthly_only_plan_has_null_yearly_price(self):
        data = self.client.get(self.url).json()[1]

        self.assertIsNone(data["price_yearly"])
        self.assertEqual(data["yearly_discount_percent"], 0)

    def test_internal_fields_are_not_exposed(self):
        data = self.client.get(self.url).json()[0]

        for hidden in ("id", "is_active", "is_public", "sort_order", "created_at"):
            self.assertNotIn(hidden, data)

    def test_inactive_and_private_plans_are_hidden(self):
        Plan.objects.create(code="old", name="Old", price_monthly=Decimal("1"), is_active=False)
        Plan.objects.create(code="deal", name="Deal", price_monthly=Decimal("1"), is_public=False)

        self.assertEqual(self.codes(self.client.get(self.url)), ["start", "pro"])

    def test_filter_by_organization_type_includes_plans_for_all(self):
        Plan.objects.create(
            code="center", name="Center", price_monthly=Decimal("1"),
            audience=Plan.Audience.LEARNING_CENTER, sort_order=3,
        )
        Plan.objects.create(
            code="school", name="School", price_monthly=Decimal("1"),
            audience=Plan.Audience.PRIVATE_SCHOOL, sort_order=4,
        )

        centers = self.client.get(self.url, {"organization_type": "learning_center"})
        schools = self.client.get(self.url, {"organization_type": "private_school"})

        self.assertEqual(self.codes(centers), ["start", "pro", "center"])
        self.assertEqual(self.codes(schools), ["start", "pro", "school"])

    def test_unknown_organization_type_is_an_error(self):
        response = self.client.get(self.url, {"organization_type": "zavod"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_detail_by_code(self):
        response = self.client.get(reverse("plan-detail", args=["pro"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Pro")

    def test_detail_hides_inactive_private_and_unknown(self):
        Plan.objects.create(code="old", name="Old", price_monthly=Decimal("1"), is_active=False)
        Plan.objects.create(code="deal", name="Deal", price_monthly=Decimal("1"), is_public=False)

        for code in ("old", "deal", "yoq"):
            response = self.client.get(reverse("plan-detail", args=[code]))
            self.assertEqual(response.status_code, 404, code)
            self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_catalog_is_read_only(self):
        for url in (self.url, reverse("plan-detail", args=["start"])):
            for method in ("post", "put", "patch", "delete"):
                response = getattr(self.client, method)(url, {"name": "X"})
                self.assertEqual(response.status_code, 405, (url, method))
        self.assertEqual(Plan.objects.count(), 2)

    def test_catalog_is_throttled_per_ip(self):
        for _ in range(120):
            self.assertEqual(self.client.get(self.url).status_code, 200)

        self.assertEqual(self.client.get(self.url).status_code, 429)
        # boshqa IP o'z hisobiga ega
        other = self.client.get(self.url, REMOTE_ADDR="10.0.0.9")
        self.assertEqual(other.status_code, 200)
        