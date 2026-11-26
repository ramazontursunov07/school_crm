from django.test import SimpleTestCase

from apps.organizations import roles
from apps.organizations.roles import Role


class RoleTests(SimpleTestCase):
    def test_every_role_has_rank_and_permissions(self):
        for role in Role.values:
            self.assertIn(role, roles.ROLE_RANK)
            self.assertIn(role, roles.ROLE_PERMISSIONS)

    def test_owner_has_every_permission(self):
        for permission in roles._ALL:
            self.assertTrue(roles.has_permission(Role.OWNER, permission))

    def test_teacher_is_read_only(self):
        self.assertTrue(roles.has_permission(Role.TEACHER, roles.ORG_VIEW))
        self.assertFalse(roles.has_permission(Role.TEACHER, roles.BRANCH_MANAGE))
        self.assertFalse(roles.has_permission(Role.TEACHER, roles.MEMBERS_INVITE))
        self.assertFalse(roles.has_permission(Role.TEACHER, roles.AUDIT_VIEW))

    def test_unknown_role_has_nothing(self):
        self.assertFalse(roles.has_permission("hacker", roles.ORG_VIEW))
        self.assertFalse(roles.can_assign("hacker", Role.TEACHER))

    def test_only_owner_manages_organization_settings(self):
        for role in Role.values:
            self.assertEqual(
                roles.has_permission(role, roles.ORG_MANAGE), role == Role.OWNER
            )

    def test_can_assign_requires_higher_rank(self):
        self.assertTrue(roles.can_assign(Role.OWNER, Role.OWNER))
        self.assertTrue(roles.can_assign(Role.DIRECTOR, Role.ADMIN))
        self.assertFalse(roles.can_assign(Role.DIRECTOR, Role.OWNER))
        self.assertFalse(roles.can_assign(Role.DIRECTOR, Role.DIRECTOR))
        self.assertFalse(roles.can_assign(Role.ADMIN, Role.DIRECTOR))
        self.assertTrue(roles.can_assign(Role.ADMIN, Role.TEACHER))
        