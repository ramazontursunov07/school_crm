from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.audit.models import AuditLog

User = get_user_model()
PASSWORD = "Kuchli-Sinov-Paroli-77"


class AuthTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # urinishlar hisobi testlar orasida qolib ketmasin
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self):
        return self.client.get(reverse("auth-csrf")).json()["csrf_token"]

    def post(self, name, data=None, token=None):
        return self.client.post(
            reverse(name), data or {}, HTTP_X_CSRFTOKEN=token or self.csrf()
        )

    def make_user(self, **fields):
        data = {
            "username": "ali",
            "email": "ali@example.com",
            "phone": "+998901234567",
        }
        data.update(fields)
        return User.objects.create_user(password=PASSWORD, **data)

    def login(self, identifier="ali", password=PASSWORD):
        return self.post("auth-login", {"identifier": identifier, "password": password})

    def me_status(self):
        return self.client.get(reverse("auth-me")).status_code


class RegisterTests(AuthTestCase):
    def register(self, **changes):
        data = {"username": "ali", "password": PASSWORD, "email": "Ali@Example.com"}
        data.update(changes)
        return self.post("auth-register", data)

    def test_register_creates_user_and_logs_in(self):
        response = self.register(phone="+998 (90) 123-45-67")

        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get()
        self.assertEqual(user.email, "ali@example.com")
        self.assertEqual(user.phone, "+998901234567")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotIn("password", response.json()["user"])
        self.assertEqual(self.me_status(), 200)
        self.assertTrue(AuditLog.objects.filter(action="user.registered").exists())

    def test_privilege_fields_are_ignored(self):
        self.assertEqual(
            self.register(is_staff=True, is_superuser=True).status_code, 201
        )

        user = User.objects.get()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_invalid_data_is_rejected(self):
        cases = [
            {"password": "12345"},
            {"email": ""},
            {"phone": "901234567"},
            {"username": "kimdir@example.com"},
            {"username": "+998901112233"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                cache.clear()
                self.assertEqual(self.register(**changes).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_duplicates_are_rejected(self):
        self.make_user()
        cases = [
            {"username": "ALI", "email": "new@example.com"},
            {"username": "vali", "email": "ALI@example.com"},
            {"username": "vali", "email": "", "phone": "+998 90 123 45 67"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.register(**changes).status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_register_requires_csrf(self):
        response = self.client.post(
            reverse("auth-register"),
            {"username": "ali", "password": PASSWORD, "email": "a@example.com"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())

    def test_register_is_throttled(self):
        for _ in range(5):
            self.register(password="1")

        self.assertEqual(self.register().status_code, 429)


class LoginLogoutTests(AuthTestCase):
    def test_login_with_username_email_or_phone(self):
        self.make_user()
        for identifier in ("ali", "ALI@example.com", "+998 90 123-45-67"):
            with self.subTest(identifier=identifier):
                self.client = APIClient(enforce_csrf_checks=True)
                self.assertEqual(self.login(identifier).status_code, 200)
                self.assertEqual(self.me_status(), 200)

    def test_wrong_password_unknown_and_inactive_get_same_answer(self):
        self.make_user()
        self.make_user(
            username="off", email="off@example.com", phone=None, is_active=False
        )
        responses = [
            self.login("ali", "xato-parol"),
            self.login("yoq@example.com"),
            self.login("off"),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 400)
        self.assertEqual(len({str(r.json()) for r in responses}), 1)
        self.assertEqual(self.me_status(), 403)

    def test_login_requires_csrf(self):
        self.make_user()
        response = self.client.post(
            reverse("auth-login"), {"identifier": "ali", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 403)

    def test_session_key_changes_on_login(self):
        self.make_user()
        session = self.client.session
        session["x"] = 1
        session.save()
        self.client.cookies["sessionid"] = session.session_key

        self.login()

        self.assertNotEqual(self.client.cookies["sessionid"].value, session.session_key)

    def test_logout_ends_session(self):
        self.make_user()
        token = self.login().json()["csrf_token"]

        self.assertEqual(self.post("auth-logout", token=token).status_code, 204)
        self.assertEqual(self.me_status(), 403)

    def test_logout_requires_csrf(self):
        self.make_user()
        self.login()

        response = self.client.post(reverse("auth-logout"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.me_status(), 200)

    def test_guessing_one_account_from_many_ips_is_throttled(self):
        self.make_user()
        token = self.csrf()

        def attempt(number, password):
            return self.client.post(
                reverse("auth-login"),
                {"identifier": "ali", "password": password},
                HTTP_X_CSRFTOKEN=token,
                REMOTE_ADDR=f"10.0.0.{number}",
            )

        for number in range(10):
            self.assertEqual(attempt(number, "xato").status_code, 400)
        self.assertEqual(attempt(99, PASSWORD).status_code, 429)

    def test_forged_forwarded_header_does_not_bypass_ip_limit(self):
        token = self.csrf()
        codes = [
            self.client.post(
                reverse("auth-login"),
                {"identifier": f"user{number}", "password": "xato"},
                HTTP_X_CSRFTOKEN=token,
                HTTP_X_FORWARDED_FOR=f"1.1.1.{number}",
            ).status_code
            for number in range(21)
        ]

        self.assertEqual(codes[-1], 429)
