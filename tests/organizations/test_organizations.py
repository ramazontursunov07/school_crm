from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Branch, Membership, Organization
from apps.organizations.roles import Role

from .helpers import TenantTestCase


class OrganizationApiTests(TenantTestCase):
    def test_anonymous_cannot_list_or_create(self):
        self.assertEqual(self.client.get(reverse("organization-list")).status_code, 403)
        response = self.client.post(reverse("organization-list"), {"name": "X"})
        self.assertEqual(response.status_code, 403)

    def test_create_makes_owner_and_main_branch(self):
        user = self.make_user("ali")
        self.login(user)

        response = self.client.post(
            reverse("organization-list"),
            {"name": "Nur o'quv markazi", "type": "learning_center", "country": "uz"},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["my_role"], "owner")
        self.assertEqual(body["country"], "UZ")
        self.assertTrue(body["slug"])
        org = Organization.objects.get(pk=body["id"])
        self.assertEqual(org.branches.count(), 1)
        membership = Membership.objects.get(user=user, organization=org)
        self.assertEqual(membership.role, Role.OWNER)
        self.assertTrue(AuditLog.objects.filter(
            organization=org, action="organization.created", actor=user
        ).exists())

    def test_create_validates_input(self):
        self.login(self.make_user("ali"))
        url = reverse("organization-list")

        bad_type = self.client.post(url, {"name": "A", "type": "zavod"})
        bad_country = self.client.post(
            url, {"name": "A", "type": "private_school", "country": "UZB"}
        )
        blank = self.client.post(url, {"name": "   ", "type": "private_school"})

        for response in (bad_type, bad_country, blank):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.error_code(response), "validation_error")
        self.assertEqual(Organization.objects.count(), 0)

    def test_same_name_gets_distinct_slugs(self):
        self.login(self.make_user("ali"))
        url = reverse("organization-list")
        data = {"name": "Nur", "type": "learning_center"}

        first = self.client.post(url, data).json()
        second = self.client.post(url, data).json()

        self.assertNotEqual(first["slug"], second["slug"])

    def test_list_shows_only_my_organizations_with_my_role(self):
        ali, vali = self.make_user("ali"), self.make_user("vali")
        mine = self.make_org("Mening", owner=ali)
        other = self.make_org("Boshqa", owner=vali)
        self.join(ali, other, Role.TEACHER)
        stranger_org = self.make_org("Begona", owner=vali)
        self.login(ali)

        response = self.client.get(reverse("organization-list"))

        roles_by_id = {o["id"]: o["my_role"] for o in response.json()["results"]}
        self.assertEqual(roles_by_id, {mine.id: "owner", other.id: "teacher"})
        self.assertNotIn(stranger_org.id, roles_by_id)

    def test_user_works_in_several_organizations_with_different_roles(self):
        ali, vali = self.make_user("ali"), self.make_user("vali")
        org_a = self.make_org("A", owner=vali)
        org_b = self.make_org("B", owner=vali)
        self.join(ali, org_a, Role.ADMIN)
        self.join(ali, org_b, Role.TEACHER)
        self.login(ali)

        # A da administrator filial yarata oladi, B da o'qituvchi yarata olmaydi
        in_a = self.client.post(reverse("branch-list", args=[org_a.id]), {"name": "Yangi"})
        in_b = self.client.post(reverse("branch-list", args=[org_b.id]), {"name": "Yangi"})

        self.assertEqual(in_a.status_code, 201)
        self.assertEqual(in_b.status_code, 403)

    def test_removed_member_loses_access(self):
        owner, teacher = self.make_user("owner"), self.make_user("teacher")
        org = self.make_org("A", owner=owner)
        membership = self.join(teacher, org, Role.TEACHER)
        membership.is_active = False
        membership.save()
        self.login(teacher)

        response = self.client.get(reverse("organization-detail", args=[org.id]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(reverse("organization-list")).json()["count"], 0)

    def test_only_owner_can_update_organization(self):
        owner, director = self.make_user("owner"), self.make_user("director")
        org = self.make_org("Eski nom", owner=owner)
        self.join(director, org, Role.DIRECTOR)
        url = reverse("organization-detail", args=[org.id])

        self.login(director)
        self.assertEqual(self.client.patch(url, {"name": "Hack"}).status_code, 403)

        self.login(owner)
        response = self.client.patch(url, {"name": "Yangi nom", "slug": "hack", "is_active": False})
        self.assertEqual(response.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.name, "Yangi nom")
        self.assertNotEqual(org.slug, "hack")
        self.assertTrue(org.is_active)
        log = AuditLog.objects.get(action="organization.updated")
        self.assertEqual(log.metadata["changes"]["name"], {"old": "Eski nom", "new": "Yangi nom"})

    def test_put_and_delete_are_not_allowed(self):
        owner = self.make_user("owner")
        org = self.make_org("A", owner=owner)
        self.login(owner)
        url = reverse("organization-detail", args=[org.id])

        self.assertEqual(self.client.put(url, {"name": "X", "type": "private_school"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_inactive_organization_is_read_only(self):
        owner = self.make_user("owner")
        org = self.make_org("A", owner=owner)
        org.is_active = False
        org.save()
        self.login(owner)

        detail = reverse("organization-detail", args=[org.id])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.patch(detail, {"name": "X"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("branch-list", args=[org.id])).status_code, 403)


class BranchApiTests(TenantTestCase):
    def setUp(self):
        self.owner = self.make_user("owner")
        self.org = self.make_org("A", owner=self.owner)
        self.url = reverse("branch-list", args=[self.org.id])

    def test_crud_and_audit(self):
        self.login(self.owner)

        created = self.client.post(
            self.url, {"name": "Chilonzor", "address": "Chilonzor 5", "phone": "+998901112233"}
        )
        self.assertEqual(created.status_code, 201)
        branch_id = created.json()["id"]
        detail = reverse("branch-detail", args=[self.org.id, branch_id])

        updated = self.client.patch(detail, {"is_active": False})
        listing = self.client.get(self.url)

        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["is_active"])
        self.assertEqual(listing.json()["count"], 2)
        actions = list(AuditLog.objects.filter(organization=self.org).values_list("action", flat=True))
        self.assertIn("branch.created", actions)
        self.assertIn("branch.updated", actions)
        self.assertEqual(self.client.delete(detail).status_code, 405)

    def test_duplicate_name_is_rejected_ignoring_case(self):
        self.login(self.owner)

        response = self.client.post(self.url, {"name": "ASOSIY FILIAL"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Branch.objects.filter(organization=self.org).count(), 1)

    def test_same_name_allowed_in_different_organizations(self):
        other_owner = self.make_user("other")
        other = self.make_org("B", owner=other_owner)
        self.login(other_owner)

        response = self.client.post(reverse("branch-list", args=[other.id]), {"name": "Yangi"})
        self.assertEqual(response.status_code, 201)
        response = self.client.post(self.url, {"name": "Yangi"})
        self.assertEqual(response.status_code, 404)

    def test_renaming_to_own_name_is_fine(self):
        self.login(self.owner)
        branch = self.org.branches.get()

        response = self.client.patch(
            reverse("branch-detail", args=[self.org.id, branch.id]),
            {"name": "Asosiy filial", "address": "Yangi manzil"},
        )

        self.assertEqual(response.status_code, 200)

    def test_read_only_roles_cannot_write(self):
        for role in (Role.ACCOUNTANT, Role.TEACHER):
            user = self.make_user(f"u_{role}")
            self.join(user, self.org, role)
            self.login(user)

            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertEqual(self.client.post(self.url, {"name": f"N {role}"}).status_code, 403)
        self.assertEqual(Branch.objects.filter(organization=self.org).count(), 1)
        