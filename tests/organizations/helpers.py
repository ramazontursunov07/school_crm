from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.organizations.models import Branch, Membership, Organization
from apps.organizations.roles import Role

User = get_user_model()


class TenantTestCase(APITestCase):
    def make_user(self, username, **fields):
        fields.setdefault("email", f"{username}@example.com")
        return User.objects.create_user(
            username=username, password="Test-parol-12345", **fields
        )

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
    