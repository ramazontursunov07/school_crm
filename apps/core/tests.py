import json

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse


class HealthTests(SimpleTestCase):
    def test_health_returns_ok(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_wrong_method_uses_common_error_format(self):
        response = self.client.post(reverse("health"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")


class ErrorFormatTests(SimpleTestCase):
    def test_unknown_api_url_uses_common_error_format(self):
        response = self.client.get("/api/v1/yoq-manzil/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_unknown_non_api_url_keeps_standard_page(self):
        response = self.client.get("/yoq-sahifa/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/html")

    def test_server_error_handler_returns_json_for_api_only(self):
        from apps.core import views

        api = views.server_error(RequestFactory().get("/api/v1/health/"))
        page = views.server_error(RequestFactory().get("/admin/"))

        self.assertEqual(api.status_code, 500)
        self.assertEqual(
            json.loads(api.content)["error"]["code"], "server_error"
        )
        self.assertEqual(page.status_code, 500)
        self.assertIn(b"text/html", page["Content-Type"].encode())

    def test_bad_request_and_forbidden_handlers_for_api(self):
        from apps.core import views

        request = RequestFactory().get("/api/v1/health/")

        self.assertEqual(json.loads(views.bad_request(request).content)["error"]["code"], "bad_request")
        self.assertEqual(
            json.loads(views.permission_denied(request).content)["error"]["code"],
            "permission_denied",
        )
