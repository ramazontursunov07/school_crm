import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import VerificationCode
from apps.audit.models import AuditLog

User = get_user_model()
PASSWORD = "Kuchli-Sinov-Paroli-77"
NEW_PASSWORD = "Yangi-Kuchli-Parol-91"


def last_code():
    """Oxirgi yuborilgan emaildagi 6 xonali kod."""
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


class CodeTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self):
        return self.client.get(reverse("auth-csrf")).json()["csrf_token"]

    def post(self, name, data=None):
        return self.client.post(reverse(name), data or {}, HTTP_X_CSRFTOKEN=self.csrf())

    def make_user(self, **fields):
        data = {"username": "ali", "email": "ali@example.com", "phone": "+998901234567"}
        data.update(fields)
        return User.objects.create_user(password=PASSWORD, **data)

    def verify(self, user, email=True, phone=False):
        now = timezone.now()
        if email:
            user.email_verified_at = now
        if phone:
            user.phone_verified_at = now
        user.save(update_fields=["email_verified_at", "phone_verified_at"])

    def login(self, identifier="ali", password=PASSWORD):
        return self.post("auth-login", {"identifier": identifier, "password": password})


class VerifyContactTests(CodeTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.login()

    def request_code(self, channel="email"):
        return self.post("auth-verify-request", {"channel": channel})

    def confirm(self, code, channel="email"):
        return self.post("auth-verify-confirm", {"channel": channel, "code": code})

    def test_email_verification_flow(self):
        response = self.request_code()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"expires_in": 600, "resend_after": 60})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ali@example.com"])

        confirmed = self.confirm(last_code())

        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertTrue(confirmed.json()["email_verified"])
        self.assertFalse(confirmed.json()["phone_verified"])
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertTrue(AuditLog.objects.filter(action="user.email_verified").exists())
        self.assertTrue(
            self.client.get(reverse("auth-me")).json()["email_verified"]
        )

    def test_code_is_not_stored_in_plain_text(self):
        self.request_code()
        stored = VerificationCode.objects.get()
        self.assertNotIn(last_code(), stored.code_hash)
        self.assertEqual(len(stored.code_hash), 64)

    def test_wrong_code_rejected_and_user_stays_unverified(self):
        self.request_code()
        wrong = "000000" if last_code() != "000000" else "111111"

        response = self.confirm(wrong)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "validation_error")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)

    def test_code_dies_after_five_wrong_attempts(self):
        self.request_code()
        correct = last_code()
        wrong = "000000" if correct != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.confirm(wrong).status_code, 400)

        self.assertEqual(self.confirm(correct).status_code, 400)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)

    def test_code_cannot_be_reused(self):
        self.request_code()
        code = last_code()
        self.assertEqual(self.confirm(code).status_code, 200)
        # Tasdiqlash bekor qilingan, lekin ishlatilgan kod qayta ishlamaydi
        self.user.email_verified_at = None
        self.user.save(update_fields=["email_verified_at"])

        self.assertEqual(self.confirm(code).status_code, 400)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)

    def test_expired_code_rejected(self):
        self.request_code()
        VerificationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(self.confirm(last_code()).status_code, 400)

    def test_new_request_invalidates_old_code(self):
        self.request_code()
        first = last_code()
        VerificationCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        self.request_code()
        second = last_code()

        if first != second:  # 1/10^6 ehtimol bilan bir xil chiqishi mumkin
            self.assertEqual(self.confirm(first).status_code, 400)
        self.assertEqual(self.confirm(second).status_code, 200)

    def test_resend_cooldown(self):
        self.assertEqual(self.request_code().status_code, 200)

        response = self.request_code()

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertEqual(len(mail.outbox), 1)

    def test_hourly_limit(self):
        for _ in range(5):
            self.assertEqual(self.request_code().status_code, 200)
            VerificationCode.objects.filter(
                created_at__gt=timezone.now() - timedelta(seconds=30)
            ).update(created_at=timezone.now() - timedelta(minutes=5))
        self.assertEqual(self.request_code().status_code, 429)

    def test_already_verified_or_missing_contact(self):
        self.verify(self.user)
        self.assertEqual(self.request_code().status_code, 400)

        other = self.make_user(username="vali", email="", phone="")
        self.login("vali")
        self.assertEqual(self.request_code().status_code, 400)

    def test_requires_login(self):
        anonymous = APIClient()
        self.assertEqual(
            anonymous.post(reverse("auth-verify-request"), {"channel": "email"}).status_code,
            403,
        )

    def test_changing_email_revokes_verification_and_old_code(self):
        self.request_code()
        code = last_code()
        self.verify(self.user)

        self.user.email = "boshqa@example.com"
        self.user.save()
        self.user.refresh_from_db()

        self.assertIsNone(self.user.email_verified_at)
        # Eski emailga yuborilgan kod yangi emailni tasdiqlay olmaydi
        self.assertEqual(self.confirm(code).status_code, 400)

    def test_phone_code_delivery_unavailable_without_provider(self):
        response = self.request_code("phone")

        self.assertEqual(response.status_code, 503)

    @override_settings(DEBUG=True)
    def test_phone_verification_flow_in_debug(self):
        with self.assertLogs("apps.accounts.delivery", "INFO") as logs:
            self.assertEqual(self.request_code("phone").status_code, 200)
        code = re.search(r"\b(\d{6})\b", logs.output[0]).group(1)

        response = self.confirm(code, channel="phone")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["phone_verified"])


class PasswordResetTests(CodeTestCase):
    def request_reset(self, identifier="ali@example.com"):
        return self.post("auth-password-reset-request", {"identifier": identifier})

    def confirm_reset(self, code, password=NEW_PASSWORD, identifier="ali@example.com"):
        return self.post(
            "auth-password-reset-confirm",
            {"identifier": identifier, "code": code, "new_password": password},
        )

    def test_reset_flow(self):
        user = self.make_user()
        self.verify(user)

        self.assertEqual(self.request_reset().status_code, 204)
        self.assertEqual(len(mail.outbox), 1)
        response = self.confirm_reset(last_code())

        self.assertEqual(response.status_code, 204, response.content)
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertEqual(self.login(password=PASSWORD).status_code, 400)
        self.assertEqual(self.login(password=NEW_PASSWORD).status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="user.password_reset").exists())

    def test_reset_by_username_uses_verified_email(self):
        user = self.make_user()
        self.verify(user)

        self.assertEqual(self.request_reset("ali").status_code, 204)

        self.assertEqual(mail.outbox[0].to, ["ali@example.com"])
        self.assertEqual(self.confirm_reset(last_code(), identifier="ali").status_code, 204)

    def test_reset_logs_out_other_sessions(self):
        user = self.make_user()
        self.verify(user)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

        self.request_reset()
        self.confirm_reset(last_code())

        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 403)

    def test_unverified_unknown_and_inactive_get_same_response_and_no_email(self):
        self.make_user()  # email tasdiqlanmagan
        self.make_user(username="vali", email="vali@example.com", phone="")
        User.objects.filter(username="vali").update(
            email_verified_at=timezone.now(), is_active=False
        )

        responses = [
            self.request_reset("ali@example.com"),
            self.request_reset("yoq@example.com"),
            self.request_reset("vali@example.com"),
        ]

        self.assertEqual([r.status_code for r in responses], [204, 204, 204])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(VerificationCode.objects.count(), 0)

    def test_wrong_code_does_not_change_password(self):
        user = self.make_user()
        self.verify(user)
        self.request_reset()
        correct = last_code()
        wrong = "000000" if correct != "000000" else "111111"

        self.assertEqual(self.confirm_reset(wrong).status_code, 400)

        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))

    def test_code_dies_after_five_wrong_attempts(self):
        user = self.make_user()
        self.verify(user)
        self.request_reset()
        correct = last_code()
        wrong = "000000" if correct != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.confirm_reset(wrong).status_code, 400)

        self.assertEqual(self.confirm_reset(correct).status_code, 400)

    def test_weak_password_rejected_without_burning_code(self):
        user = self.make_user()
        self.verify(user)
        self.request_reset()
        code = last_code()

        weak = self.confirm_reset(code, password="12345678")

        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.json()["error"]["details"])
        self.assertEqual(self.confirm_reset(code).status_code, 204)

    def test_confirm_for_unknown_account_looks_like_wrong_code(self):
        response = self.confirm_reset("123456", identifier="yoq@example.com")

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.json()["error"]["details"])

    def test_reset_code_cannot_verify_contact(self):
        user = self.make_user()
        self.verify(user)
        self.request_reset()
        code = last_code()
        self.login()

        response = self.post("auth-verify-confirm", {"channel": "email", "code": code})

        self.assertEqual(response.status_code, 400)

    def test_request_is_throttled_per_account(self):
        user = self.make_user()
        self.verify(user)
        statuses = [self.request_reset().status_code for _ in range(12)]

        self.assertEqual(statuses[:10], [204] * 10)
        self.assertEqual(statuses[10], 429)

    @override_settings(DEBUG=True)
    def test_reset_by_verified_phone(self):
        user = self.make_user()
        self.verify(user, email=False, phone=True)

        with self.assertLogs("apps.accounts.delivery", "INFO") as logs:
            self.assertEqual(self.request_reset("+998901234567").status_code, 204)
        code = re.search(r"\b(\d{6})\b", logs.output[0]).group(1)

        response = self.confirm_reset(code, identifier="+998901234567")

        self.assertEqual(response.status_code, 204, response.content)
