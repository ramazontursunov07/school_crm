from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class RequestSafetyTests(SimpleTestCase):
    def test_form_encoded_body_is_rejected(self):
        response = self.client.post(
            reverse("auth-token-login"),
            "identifier=ali&password=x",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("error", response.json())

    @override_settings(API_MAX_JSON_BODY=100)
    def test_large_json_is_rejected_before_parsing(self):
        response = self.client.post(
            reverse("auth-token-login"),
            {"identifier": "a" * 500, "password": "x"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "request_too_large")

    @override_settings(API_MAX_JSON_BODY=100)
    def test_limit_applies_only_to_api(self):
        response = self.client.get("/yoq-sahifa/", CONTENT_LENGTH="5000")
        self.assertEqual(response.status_code, 404)
        