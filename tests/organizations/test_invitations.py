from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import Invitation, Membership, hash_token
from apps.organizations.roles import Role

from .helpers import TenantTestCase


class InvitationTests(TenantTestCase):
    def setUp(self):
        self.owner = self.make_user("owner")
        self.org = self.make_org("A", owner=self.owner)
        self.url = reverse("invitation-list", args=[self.org.id])
        self.accept_url = reverse("invitation-accept")

    def invite(self, **data):
        data.setdefault("role", "teacher")
        return self.client.post(self.url, data)

    def test_create_returns_token_once_and_stores_only_hash(self):
        self.login(self.owner)

        response = self.invite(email="  Vali@Example.com ")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        invitation = Invitation.objects.get(pk=body["id"])
        self.assertEqual(invitation.email, "vali@example.com")
        self.assertEqual(invitation.token_hash, hash_token(body["token"]))
        self.assertNotIn(body["token"], invitation.token_hash)
        listing = self.client.get(self.url).json()["results"][0]
        self.assertNotIn("token", listing)
        self.assertNotIn("token_hash", listing)
        self.assertTrue(AuditLog.objects.filter(action="invitation.created").exists())

    def test_needs_email_or_phone(self):
        self.login(self.owner)

        self.assertEqual(self.invite().status_code, 400)
        self.assertEqual(self.invite(email="", phone="  ").status_code, 400)

    def test_invalid_role_rejected(self):
        self.login(self.owner)

        self.assertEqual(self.invite(email="a@example.com", role="superuser").status_code, 400)

    def test_admin_cannot_invite_equal_or_higher_roles(self):
        admin = self.make_user("admin")
        self.join(admin, self.org, Role.ADMIN)
        self.login(admin)

        for role in ("owner", "director", "admin"):
            response = self.invite(email=f"{role}@example.com", role=role)
            self.assertEqual(response.status_code, 400, role)
        self.assertEqual(self.invite(email="t@example.com", role="teacher").status_code, 201)

    def test_teacher_cannot_invite_or_list(self):
        teacher = self.make_user("teacher")
        self.join(teacher, self.org, Role.TEACHER)
        self.login(teacher)

        self.assertEqual(self.invite(email="a@example.com").status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_duplicate_pending_invitation_rejected(self):
        self.login(self.owner)
        self.invite(email="vali@example.com")

        response = self.invite(email="VALI@example.com", role="admin")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Invitation.objects.count(), 1)

    def test_cannot_invite_existing_member(self):
        vali = self.make_user("vali")
        self.join(vali, self.org, Role.TEACHER)
        self.login(self.owner)

        self.assertEqual(self.invite(email="vali@example.com").status_code, 400)

    def test_reinvite_after_expiry_or_revoke(self):
        self.login(self.owner)
        first = self.invite(email="vali@example.com").json()
        Invitation.objects.filter(pk=first["id"]).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertEqual(self.client.get(self.url).json()["results"][0]["status"], "expired")

        second = self.invite(email="vali@example.com")
        self.assertEqual(second.status_code, 201)

        revoked = self.client.delete(reverse("invitation-detail", args=[self.org.id, second.json()["id"]]))
        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(self.invite(email="vali@example.com").status_code, 201)

    def test_accept_creates_membership(self):
        branch = self.org.branches.get()
        self.login(self.owner)
        token = self.invite(email="vali@example.com", role="accountant", branch=branch.id).json()["token"]
        vali = self.make_user("vali")
        self.login(vali)

        response = self.client.post(self.accept_url, {"token": token})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["my_role"], "accountant")
        membership = Membership.objects.get(user=vali, organization=self.org)
        self.assertEqual(membership.role, Role.ACCOUNTANT)
        self.assertEqual(membership.branch, branch)
        invitation = Invitation.objects.get()
        self.assertEqual(invitation.status, Invitation.Status.ACCEPTED)
        self.assertEqual(invitation.accepted_by, vali)
        self.assertTrue(AuditLog.objects.filter(action="invitation.accepted", actor=vali).exists())

    def test_accept_by_phone(self):
        self.login(self.owner)
        token = self.invite(phone="+998901234567").json()["token"]
        vali = self.make_user("vali", phone="+998901234567")
        self.login(vali)

        self.assertEqual(self.client.post(self.accept_url, {"token": token}).status_code, 200)

    def test_token_cannot_be_reused(self):
        self.login(self.owner)
        token = self.invite(email="vali@example.com").json()["token"]
        vali = self.make_user("vali")
        self.login(vali)
        self.client.post(self.accept_url, {"token": token})
        vali_memberships = Membership.objects.filter(user=vali).count()

        again = self.client.post(self.accept_url, {"token": token})

        self.assertEqual(again.status_code, 400)
        self.assertEqual(Membership.objects.filter(user=vali).count(), vali_memberships)

    def test_wrong_account_cannot_accept(self):
        self.login(self.owner)
        token = self.invite(email="vali@example.com").json()["token"]
        eve = self.make_user("eve")
        self.login(eve)

        response = self.client.post(self.accept_url, {"token": token})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Membership.objects.filter(user=eve, organization=self.org).exists())
        self.assertEqual(Invitation.objects.get().status, Invitation.Status.PENDING)

    def test_user_without_contacts_cannot_accept(self):
        self.login(self.owner)
        token = self.invite(email="vali@example.com").json()["token"]
        nobody = self.make_user("nobody", email="")
        self.login(nobody)

        self.assertEqual(self.client.post(self.accept_url, {"token": token}).status_code, 400)

    def test_expired_revoked_and_unknown_tokens_rejected(self):
        self.login(self.owner)
        expired = self.invite(email="a@example.com").json()
        revoked = self.invite(email="b@example.com").json()
        Invitation.objects.filter(pk=expired["id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.client.delete(reverse("invitation-detail", args=[self.org.id, revoked["id"]]))

        cases = (
            ("a@example.com", expired["token"]),
            ("b@example.com", revoked["token"]),
            ("c@example.com", "yoq-token"),
        )
        for index, (email, token) in enumerate(cases):
            user = self.make_user(f"user{index}", email=email)
            self.login(user)
            response = self.client.post(self.accept_url, {"token": token})
            self.assertEqual(response.status_code, 400, token)
        self.assertEqual(Membership.objects.filter(organization=self.org).count(), 1)

    def test_accept_requires_login(self):
        self.assertEqual(self.client.post(self.accept_url, {"token": "x"}).status_code, 403)

    def test_removed_member_can_rejoin_via_new_invitation(self):
        vali = self.make_user("vali")
        old = self.join(vali, self.org, Role.DIRECTOR, is_active=False)
        self.login(self.owner)
        token = self.invite(email="vali@example.com", role="teacher").json()["token"]
        self.login(vali)

        self.assertEqual(self.client.post(self.accept_url, {"token": token}).status_code, 200)

        old.refresh_from_db()
        self.assertTrue(old.is_active)
        self.assertEqual(old.role, Role.TEACHER)
        self.assertEqual(Membership.objects.filter(user=vali).count(), 1)

    def test_revoke_rules(self):
        admin = self.make_user("admin")
        self.join(admin, self.org, Role.ADMIN)
        self.login(self.owner)
        director_inv = self.invite(email="d@example.com", role="director").json()
        self.login(admin)

        denied = self.client.delete(reverse("invitation-detail", args=[self.org.id, director_inv["id"]]))
        self.assertEqual(denied.status_code, 403)

        self.login(self.owner)
        url = reverse("invitation-detail", args=[self.org.id, director_inv["id"]])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 400)
        