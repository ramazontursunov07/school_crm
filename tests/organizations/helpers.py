from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.organizations.models import Branch, Membership, Organization
from apps.organizations.roles import Role

User = get_user_model()


class TenantTestCase(APITestCase):
    def make_user(self, username, verified=True, **fields):
        fields.setdefault("email", f"{username}@example.com")
        user = User.objects.create_user(
            username=username, password="Test-parol-12345", **fields
        )
        if verified:
            # Kontaktlar tasdiqlangan deb olinadi (taklifni qabul qilish uchun kerak)
            now = timezone.now()
            User.objects.filter(pk=user.pk).update(
                email_verified_at=now if user.email else None,
                phone_verified_at=now if user.phone else None,
            )
            user.refresh_from_db()
        return user

    def make_org(self, name, owner=None):
        org = Organization.objects.create(
            name=name, type=Organization.Type.LEARNING_CENTER
        )
        Branch.objects.create(organization=org, name="Asosiy filial")
        if owner is not None:
            Membership.objects.create(user=owner, organization=org, role=Role.OWNER)
        return org

    def join(self, user, org, role, **fields):
        return Membership.objects.create(
            user=user, organization=org, role=role, **fields
        )

    def login(self, user):
        self.client.force_authenticate(user)

    def error_code(self, response):
        return response.json()["error"]["code"]
