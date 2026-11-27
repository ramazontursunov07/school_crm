from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import DeviceToken
from apps.accounts.tokens import MAX_DEVICES
from apps.audit.models import AuditLog

User = get_user_model()
PASSWORD = "Kuchli-Sinov-Paroli-77"


class TokenTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="ali", email="ali@example.com", password=PASSWORD
        )

    def token_login(self, identifier="ali", password=PASSWORD, **extra):
        # Mobil mijoz: CSRF ham, cookie ham yo'q
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            reverse("auth-token-login"),
            {"identifier": identifier, "password": password, **extra},
        )
        return client, response

    def bearer_client(self, raw_token):
        client = APIClient(enforce_csrf_checks=True)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        return client

    def issue(self, **extra):
        _, response = self.token_login(**extra)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()


class TokenLoginTests(TokenTestCase):
    def test_login_returns_token_without_csrf(self):
        data = self.issue(device_name="Pixel 8")

        self.assertEqual(data["token_type"], "Bearer")
        self.assertEqual(data["user"]["username"], "ali")
        token = DeviceToken.objects.get()
        self.assertEqual(token.device_name, "Pixel 8")
        self.assertNotEqual(token.token_hash, data["token"])  # xom holda saqlanmaydi
        self.assertTrue(AuditLog.objects.filter(action="user.token_issued").exists())

    def test_login_by_email(self):
        self.assertEqual(self.token_login("ali@example.com")[1].status_code, 201)

    def test_wrong_password(self):
        _, response = self.token_login(password="xato-parol-123")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DeviceToken.objects.exists())

    def test_inactive_user_cannot_login(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.token_login()[1].status_code, 400)

    def test_stale_token_header_does_not_block_login(self):
        client = APIClient(enforce_csrf_checks=True)
        client.credentials(HTTP_AUTHORIZATION="Bearer eskirgan-token")
        response = client.post(
            reverse("auth-token-login"), {"identifier": "ali", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 201)

    def test_login_is_throttled_per_identifier(self):
        for _ in range(10):
            self.token_login(password="xato-parol-123")
        _, response = self.token_login(password="xato-parol-123")
        self.assertEqual(response.status_code, 429)


class TokenAuthTests(TokenTestCase):
    def test_token_authenticates_without_csrf(self):
        raw = self.issue()["token"]
        client = self.bearer_client(raw)

        self.assertEqual(client.get(reverse("auth-me")).status_code, 200)
        self.assertEqual(
            client.post(reverse("auth-device-revoke-all")).status_code, 204
        )  # POST, CSRF'siz

    def test_invalid_token_is_rejected(self):
        client = self.bearer_client("yaroqsiz")
        self.assertEqual(client.get(reverse("auth-me")).status_code, 403)

    def test_malformed_header_is_rejected(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer a b")
        self.assertEqual(client.get(reverse("auth-me")).status_code, 403)

    def test_expired_token_is_rejected(self):
        raw = self.issue()["token"]
        DeviceToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.bearer_client(raw).get(reverse("auth-me")).status_code, 403)

    def test_absolute_lifetime_is_enforced(self):
        raw = self.issue()["token"]
        DeviceToken.objects.update(created_at=timezone.now() - timedelta(days=181))
        self.assertEqual(self.bearer_client(raw).get(reverse("auth-me")).status_code, 403)

    def test_deactivated_user_token_stops_working(self):
        raw = self.issue()["token"]
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.bearer_client(raw).get(reverse("auth-me")).status_code, 403)

    def test_use_extends_idle_expiry(self):
        raw = self.issue()["token"]
        old = timezone.now() - timedelta(days=10)
        DeviceToken.objects.update(
            last_used_at=old, expires_at=old + timedelta(days=30)
        )
        self.bearer_client(raw).get(reverse("auth-me"))
        token = DeviceToken.objects.get()
        self.assertGreater(token.last_used_at, old)
        self.assertGreater(token.expires_at, old + timedelta(days=30))

    def test_session_login_does_not_create_tokens(self):
        client = APIClient()
        client.force_login(self.user)
        self.assertEqual(client.get(reverse("auth-me")).status_code, 200)
        self.assertFalse(DeviceToken.objects.exists())


class DeviceTests(TokenTestCase):
    def test_logout_current_device(self):
        raw = self.issue()["token"]
        client = self.bearer_client(raw)

        self.assertEqual(client.delete(reverse("auth-token-current")).status_code, 204)
        self.assertEqual(client.get(reverse("auth-me")).status_code, 403)

    def test_current_logout_requires_token(self):
        client = APIClient()
        client.force_login(self.user)
        self.assertEqual(client.delete(reverse("auth-token-current")).status_code, 401)

    def test_device_list_marks_current(self):
        first = self.issue(device_name="Telefon")
        second = self.issue(device_name="Planshet")
        response = self.bearer_client(first["token"]).get(reverse("auth-device-list"))

        self.assertEqual(response.status_code, 200)
        by_id = {item["id"]: item for item in response.json()}
        self.assertEqual(len(by_id), 2)
        self.assertTrue(by_id[first["device_id"]]["is_current"])
        self.assertFalse(by_id[second["device_id"]]["is_current"])
        self.assertNotIn("token", by_id[first["device_id"]])

    def test_revoke_other_device(self):
        first = self.issue()
        second = self.issue()
        client = self.bearer_client(first["token"])

        url = reverse("auth-device-detail", args=[second["device_id"]])
        self.assertEqual(client.delete(url).status_code, 204)
        self.assertEqual(
            self.bearer_client(second["token"]).get(reverse("auth-me")).status_code, 403
        )
        self.assertEqual(client.get(reverse("auth-me")).status_code, 200)

    def test_cannot_revoke_someone_elses_device(self):
        other = User.objects.create_user(username="vali", password=PASSWORD)
        _, response = self.token_login("vali")
        other_id = response.json()["device_id"]
        mine = self.bearer_client(self.issue()["token"])

        response = mine.delete(reverse("auth-device-detail", args=[other_id]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            DeviceToken.objects.get(pk=other_id, user=other).revoked_at is None
        )

    def test_revoke_all(self):
        tokens = [self.issue()["token"] for _ in range(3)]
        client = self.bearer_client(tokens[0])

        self.assertEqual(client.post(reverse("auth-device-revoke-all")).status_code, 204)
        for raw in tokens:
            self.assertEqual(
                self.bearer_client(raw).get(reverse("auth-me")).status_code, 403
            )

    def test_oldest_device_is_dropped_over_limit(self):
        issued = []
        for _ in range(MAX_DEVICES + 1):
            cache.clear()  # login cheklovi (10/soat) bu testga xalaqit bermasin
            issued.append(self.issue())

        active = DeviceToken.objects.filter(revoked_at__isnull=True)
        self.assertEqual(active.count(), MAX_DEVICES)
        self.assertFalse(active.filter(pk=issued[0]["device_id"]).exists())
        self.assertTrue(active.filter(pk=issued[-1]["device_id"]).exists())

    def test_password_reset_revokes_tokens(self):
        from apps.accounts.models import VerificationCode
        from apps.accounts.services import issue_code

        raw = self.issue()["token"]
        User.objects.filter(pk=self.user.pk).update(email_verified_at=timezone.now())
        self.user.refresh_from_db()
        code = issue_code(
            user=self.user,
            purpose=VerificationCode.Purpose.PASSWORD_RESET,
            target=self.user.email,
        )
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(reverse("auth-csrf")).json()["csrf_token"]
        response = client.post(
            reverse("auth-password-reset-confirm"),
            {
                "identifier": "ali@example.com",
                "code": code,
                "new_password": "Yangi-Kuchli-Parol-88",
            },
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.bearer_client(raw).get(reverse("auth-me")).status_code, 403)
