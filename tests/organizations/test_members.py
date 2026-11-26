from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.organizations.roles import Role

from .helpers import TenantTestCase


class MemberTests(TenantTestCase):
    def setUp(self):
        self.owner = self.make_user("owner")
        self.org = self.make_org("A", owner=self.owner)
        self.owner_m = Membership.objects.get(user=self.owner)
        self.director = self.make_user("director")
        self.director_m = self.join(self.director, self.org, Role.DIRECTOR)
        self.admin = self.make_user("admin")
        self.admin_m = self.join(self.admin, self.org, Role.ADMIN)
        self.teacher = self.make_user("teacher")
        self.teacher_m = self.join(self.teacher, self.org, Role.TEACHER)

    def url(self, membership):
        return reverse("member-detail", args=[self.org.id, membership.id])

    def test_every_member_can_list_colleagues(self):
        self.login(self.teacher)

        response = self.client.get(reverse("member-list", args=[self.org.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 4)
        first = response.json()["results"][0]
        self.assertNotIn("password", first["user"])

    def test_admin_changes_teacher_role_and_deactivates(self):
        self.login(self.admin)

        promoted = self.client.patch(self.url(self.teacher_m), {"role": "accountant"})
        removed = self.client.patch(self.url(self.teacher_m), {"is_active": False})

        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(removed.status_code, 200)
        self.teacher_m.refresh_from_db()
        self.assertEqual(self.teacher_m.role, Role.ACCOUNTANT)
        self.assertFalse(self.teacher_m.is_active)
        logs = AuditLog.objects.filter(action="membership.updated")
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs.first().metadata["user_id"], self.teacher.id)

    def test_admin_cannot_touch_higher_or_equal_roles(self):
        other_admin = self.make_user("admin2")
        other_admin_m = self.join(other_admin, self.org, Role.ADMIN)
        self.login(self.admin)

        for target in (self.owner_m, self.director_m, other_admin_m):
            response = self.client.patch(self.url(target), {"is_active": False})
            self.assertEqual(response.status_code, 403)
            target.refresh_from_db()
            self.assertTrue(target.is_active)

    def test_cannot_grant_role_at_or_above_own(self):
        self.login(self.admin)

        for role in ("admin", "director", "owner"):
            response = self.client.patch(self.url(self.teacher_m), {"role": role})
            self.assertEqual(response.status_code, 403, role)
        self.teacher_m.refresh_from_db()
        self.assertEqual(self.teacher_m.role, Role.TEACHER)

    def test_cannot_change_own_membership(self):
        self.login(self.director)

        for data in ({"role": "owner"}, {"is_active": False}):
            self.assertEqual(self.client.patch(self.url(self.director_m), data).status_code, 403)

    def test_teacher_cannot_manage_members(self):
        self.login(self.teacher)

        response = self.client.patch(self.url(self.admin_m), {"is_active": False})

        self.assertEqual(response.status_code, 403)

    def test_owner_can_demote_another_owner_when_two_exist(self):
        second = self.make_user("second")
        self.join(second, self.org, Role.OWNER)
        self.login(second)

        response = self.client.patch(self.url(self.owner_m), {"role": "director"})

        self.assertEqual(response.status_code, 200)

    def test_last_active_owner_is_protected(self):
        # API orqali bu holatga yetib bo'lmaydi (so'rov yuboruvchi o'zi ega
        # bo'lishi kerak), shuning uchun himoya servisda to'g'ridan-to'g'ri
        # tekshiriladi: faol egasi bitta bo'lgan tashkilotni egasiz qoldirib
        # bo'lmaydi.
        from rest_framework.exceptions import ValidationError

        from apps.organizations import services

        ghost = self.make_user("ghost")
        ghost_m = self.join(ghost, self.org, Role.OWNER, is_active=False)

        for changes in ({"is_active": False}, {"role": Role.DIRECTOR}):
            with self.assertRaises(ValidationError):
                services.update_membership(
                    target=self.owner_m, actor_membership=ghost_m, changes=changes
                )
        self.owner_m.refresh_from_db()
        self.assertTrue(self.owner_m.is_active)
        self.assertEqual(self.owner_m.role, Role.OWNER)

    def test_branch_assignment_only_within_organization(self):
        other_owner = self.make_user("other")
        other_org = self.make_org("B", owner=other_owner)
        foreign_branch = other_org.branches.get()
        own_branch = self.org.branches.get()
        self.login(self.owner)

        foreign = self.client.patch(self.url(self.teacher_m), {"branch": foreign_branch.id})
        own = self.client.patch(self.url(self.teacher_m), {"branch": own_branch.id})
        cleared = self.client.patch(self.url(self.teacher_m), {"branch": None})

        self.assertEqual(foreign.status_code, 400)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["branch"], own_branch.id)
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["branch"])

    def test_invalid_role_value_rejected(self):
        self.login(self.owner)

        response = self.client.patch(self.url(self.teacher_m), {"role": "god"})

        self.assertEqual(response.status_code, 400)
        