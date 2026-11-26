from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Branch, Invitation, Membership
from apps.organizations.roles import Role

from .helpers import TenantTestCase


class TenantIsolationTests(TenantTestCase):
    """A tashkilot foydalanuvchisi B tashkilot ma'lumotiga hech qanday yo'l
    bilan yeta olmasligi kerak, hatto A da egasi bo'lsa ham."""

    def setUp(self):
        self.alice = self.make_user("alice")
        self.bob = self.make_user("bob")
        self.org_a = self.make_org("A", owner=self.alice)
        self.org_b = self.make_org("B", owner=self.bob)
        self.branch_b = self.org_b.branches.get()
        self.member_b = Membership.objects.get(user=self.bob)
        self.invitation_b, _ = Invitation.create_with_token(
            organization=self.org_b,
            email="x@example.com",
            role=Role.TEACHER,
            invited_by=self.bob,
            expires_at="2999-01-01T00:00:00+00:00",
        )
        self.login(self.alice)

    def test_foreign_organization_is_invisible_everywhere(self):
        org = self.org_b.id
        urls = [
            reverse("organization-detail", args=[org]),
            reverse("branch-list", args=[org]),
            reverse("branch-detail", args=[org, self.branch_b.id]),
            reverse("member-list", args=[org]),
            reverse("member-detail", args=[org, self.member_b.id]),
            reverse("invitation-list", args=[org]),
            reverse("audit-log-list", args=[org]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404, url)
            self.assertEqual(self.error_code(response), "not_found", url)

    def test_foreign_organization_cannot_be_written(self):
        org = self.org_b.id
        attempts = [
            ("patch", reverse("organization-detail", args=[org]), {"name": "Hack"}),
            ("post", reverse("branch-list", args=[org]), {"name": "Hack"}),
            ("patch", reverse("branch-detail", args=[org, self.branch_b.id]), {"name": "Hack"}),
            ("patch", reverse("member-detail", args=[org, self.member_b.id]), {"is_active": False}),
            ("post", reverse("invitation-list", args=[org]), {"email": "e@example.com", "role": "teacher"}),
            ("delete", reverse("invitation-detail", args=[org, self.invitation_b.id]), None),
        ]
        for method, url, data in attempts:
            response = getattr(self.client, method)(url, data) if data else getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 404, (method, url))

        self.org_b.refresh_from_db()
        self.branch_b.refresh_from_db()
        self.member_b.refresh_from_db()
        self.invitation_b.refresh_from_db()
        self.assertEqual(self.org_b.name, "B")
        self.assertEqual(self.branch_b.name, "Asosiy filial")
        self.assertTrue(self.member_b.is_active)
        self.assertEqual(self.invitation_b.status, Invitation.Status.PENDING)
        self.assertEqual(Branch.objects.filter(organization=self.org_b).count(), 1)

    def test_foreign_object_ids_via_own_organization_url_are_404(self):
        org = self.org_a.id

        for url in (
            reverse("branch-detail", args=[org, self.branch_b.id]),
            reverse("member-detail", args=[org, self.member_b.id]),
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        response = self.client.patch(
            reverse("member-detail", args=[org, self.member_b.id]), {"is_active": False}
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.delete(
            reverse("invitation-detail", args=[org, self.invitation_b.id])
        )
        self.assertEqual(response.status_code, 404)
        self.invitation_b.refresh_from_db()
        self.assertEqual(self.invitation_b.status, Invitation.Status.PENDING)

    def test_foreign_branch_cannot_be_used_in_invitation(self):
        response = self.client.post(
            reverse("invitation-list", args=[self.org_a.id]),
            {"email": "n@example.com", "role": "teacher", "branch": self.branch_b.id},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Invitation.objects.filter(email="n@example.com").exists())

    def test_lists_contain_only_own_data(self):
        self.client.post(reverse("branch-list", args=[self.org_a.id]), {"name": "A filiali"})
        self.login(self.bob)
        self.client.post(reverse("branch-list", args=[self.org_b.id]), {"name": "B filiali"})
        self.login(self.alice)

        branches = self.client.get(reverse("branch-list", args=[self.org_a.id])).json()["results"]
        members = self.client.get(reverse("member-list", args=[self.org_a.id])).json()["results"]
        logs = self.client.get(reverse("audit-log-list", args=[self.org_a.id])).json()["results"]

        self.assertEqual({b["name"] for b in branches}, {"Asosiy filial", "A filiali"})
        self.assertEqual([m["user"]["username"] for m in members], ["alice"])
        self.assertEqual([log["metadata"]["name"] for log in logs], ["A filiali"])

    def test_nonexistent_and_foreign_organizations_look_the_same(self):
        foreign = self.client.get(reverse("branch-list", args=[self.org_b.id]))
        missing = self.client.get(reverse("branch-list", args=[999999]))

        self.assertEqual(foreign.status_code, missing.status_code)
        self.assertEqual(foreign.json(), missing.json())

    def test_unauthenticated_gets_no_data(self):
        self.client.force_authenticate(None)

        for url in (
            reverse("organization-list"),
            reverse("branch-list", args=[self.org_a.id]),
            reverse("member-list", args=[self.org_a.id]),
            reverse("audit-log-list", args=[self.org_a.id]),
        ):
            self.assertEqual(self.client.get(url).status_code, 403, url)


class AuditLogTests(TenantTestCase):
    def setUp(self):
        self.owner = self.make_user("owner")
        self.org = self.make_org("A", owner=self.owner)
        self.url = reverse("audit-log-list", args=[self.org.id])

    def test_only_owner_and_director_can_read(self):
        allowed = {Role.OWNER: True, Role.DIRECTOR: True, Role.ADMIN: False,
                   Role.ACCOUNTANT: False, Role.TEACHER: False}
        for role, ok in allowed.items():
            user = self.owner if role == Role.OWNER else self.make_user(f"u_{role}")
            if role != Role.OWNER:
                self.join(user, self.org, role)
            self.login(user)

            self.assertEqual(self.client.get(self.url).status_code, 200 if ok else 403, role)

    def test_log_records_actor_ip_and_filters_by_action(self):
        self.login(self.owner)
        self.client.post(reverse("branch-list", args=[self.org.id]), {"name": "Yangi"})
        self.client.patch(reverse("organization-detail", args=[self.org.id]), {"name": "Yangi nom"})

        everything = self.client.get(self.url).json()["results"]
        only_branch = self.client.get(self.url, {"action": "branch.created"}).json()["results"]

        self.assertEqual([e["action"] for e in everything], ["organization.updated", "branch.created"])
        self.assertEqual(len(only_branch), 1)
        self.assertEqual(only_branch[0]["actor"]["username"], "owner")
        self.assertEqual(only_branch[0]["ip_address"], "127.0.0.1")

    def test_log_entries_are_append_only(self):
        self.login(self.owner)
        self.client.post(reverse("branch-list", args=[self.org.id]), {"name": "Yangi"})
        entry = AuditLog.objects.get()

        entry.action = "hack"
        with self.assertRaises(ValueError):
            entry.save()
        with self.assertRaises(ValueError):
            entry.delete()
        self.assertEqual(AuditLog.objects.get().action, "branch.created")

    def test_log_survives_actor_deletion(self):
        self.login(self.owner)
        self.client.post(reverse("branch-list", args=[self.org.id]), {"name": "Yangi"})
        owner_id = self.owner.id
        extra = self.make_user("extra")
        self.join(extra, self.org, Role.DIRECTOR)
        self.login(extra)
        self.client.post(reverse("branch-list", args=[self.org.id]), {"name": "Yana"})

        extra.delete()

        entry = AuditLog.objects.get(action="branch.created", metadata__name="Yana")
        self.assertIsNone(entry.actor)
        self.assertEqual(AuditLog.objects.filter(actor_id=owner_id).count(), 1)
