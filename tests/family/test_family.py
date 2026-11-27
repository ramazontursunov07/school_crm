from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.audit.models import AuditLog
from apps.family.models import FamilyInvite, ParentChildLink
from apps.family.services import (
    MAX_ACTIVE_INVITES,
    children_of,
    is_parent_of,
    parents_of,
)

User = get_user_model()
PASSWORD = "Kuchli-Sinov-Paroli-77"


class FamilyTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        # Ota-onaning email'i tasdiqlangan; farzandda kontakt shart emas
        self.parent = User.objects.create_user(
            username="ota", email="ota@example.com", password=PASSWORD,
            first_name="Ota", last_name="Karimov",
        )
        User.objects.filter(pk=self.parent.pk).update(email_verified_at=timezone.now())
        self.parent.refresh_from_db()
        self.child = User.objects.create_user(username="bola", password=PASSWORD)
        self.stranger = User.objects.create_user(username="begona", password=PASSWORD)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def make_invite(self, user, role):
        response = self.client_for(user).post(reverse("family-invite-list"), {"role": role})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def accept(self, user, code):
        return self.client_for(user).post(reverse("family-accept"), {"code": code})

    def link(self):
        code = self.make_invite(self.parent, "parent")["code"]
        response = self.accept(self.child, code)
        self.assertEqual(response.status_code, 201, response.content)
        return ParentChildLink.objects.get()


class InviteTests(FamilyTestCase):
    def test_requires_login(self):
        self.assertEqual(
            APIClient().post(reverse("family-invite-list"), {"role": "parent"}).status_code,
            403,
        )

    def test_code_is_shown_once_and_stored_hashed(self):
        data = self.make_invite(self.parent, "parent")

        invite = FamilyInvite.objects.get()
        self.assertEqual(len(data["code"]), 8)
        self.assertNotIn(data["code"], invite.code_hash)
        listing = self.client_for(self.parent).get(reverse("family-invite-list")).json()
        self.assertEqual(len(listing), 1)
        self.assertNotIn("code", listing[0])

    def test_unverified_user_cannot_create_parent_invite(self):
        response = self.client_for(self.stranger).post(
            reverse("family-invite-list"), {"role": "parent"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FamilyInvite.objects.exists())

    def test_child_invite_does_not_need_verified_contact(self):
        self.make_invite(self.child, "child")

    def test_invalid_role(self):
        response = self.client_for(self.parent).post(
            reverse("family-invite-list"), {"role": "admin"}
        )
        self.assertEqual(response.status_code, 400)

    def test_active_invite_limit(self):
        for _ in range(MAX_ACTIVE_INVITES):
            self.make_invite(self.parent, "parent")
        response = self.client_for(self.parent).post(
            reverse("family-invite-list"), {"role": "parent"}
        )
        self.assertEqual(response.status_code, 400)

    def test_cancel_invite(self):
        data = self.make_invite(self.parent, "parent")
        url = reverse("family-invite-detail", args=[data["id"]])

        self.assertEqual(self.client_for(self.parent).delete(url).status_code, 204)
        self.assertEqual(self.accept(self.child, data["code"]).status_code, 400)

    def test_cannot_cancel_someone_elses_invite(self):
        data = self.make_invite(self.parent, "parent")
        url = reverse("family-invite-detail", args=[data["id"]])
        self.assertEqual(self.client_for(self.stranger).delete(url).status_code, 404)


class AcceptTests(FamilyTestCase):
    def test_parent_creates_child_accepts(self):
        link = self.link()

        self.assertEqual((link.parent, link.child), (self.parent, self.child))
        self.assertTrue(AuditLog.objects.filter(action="family.linked").exists())
        self.assertTrue(FamilyInvite.objects.get().used_at)

    def test_child_creates_parent_accepts(self):
        code = self.make_invite(self.child, "child")["code"]

        response = self.accept(self.parent, code)

        self.assertEqual(response.status_code, 201, response.content)
        link = ParentChildLink.objects.get()
        self.assertEqual((link.parent, link.child), (self.parent, self.child))
        self.assertEqual(response.json()["relation"], "child")  # ota-onaga farzand

    def test_unverified_parent_cannot_accept_as_parent(self):
        code = self.make_invite(self.child, "child")["code"]

        response = self.accept(self.stranger, code)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ParentChildLink.objects.exists())

    def test_code_is_single_use(self):
        code = self.make_invite(self.parent, "parent")["code"]
        self.assertEqual(self.accept(self.child, code).status_code, 201)
        self.assertEqual(self.accept(self.stranger, code).status_code, 400)
        self.assertEqual(ParentChildLink.objects.count(), 1)

    def test_code_is_case_and_space_insensitive(self):
        code = self.make_invite(self.parent, "parent")["code"]
        spaced = f" {code[:4].lower()}-{code[4:].lower()} "
        self.assertEqual(self.accept(self.child, spaced).status_code, 201)

    def test_wrong_code(self):
        self.make_invite(self.parent, "parent")
        response = self.accept(self.child, "AAAAAAAA")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_expired_code(self):
        code = self.make_invite(self.parent, "parent")["code"]
        FamilyInvite.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.accept(self.child, code).status_code, 400)

    def test_cannot_accept_own_code(self):
        code = self.make_invite(self.parent, "parent")["code"]
        self.assertEqual(self.accept(self.parent, code).status_code, 400)

    def test_inactive_creator_code_is_rejected(self):
        code = self.make_invite(self.parent, "parent")["code"]
        User.objects.filter(pk=self.parent.pk).update(is_active=False)
        self.assertEqual(self.accept(self.child, code).status_code, 400)

    def test_cannot_link_twice_or_in_reverse(self):
        self.link()
        code = self.make_invite(self.parent, "parent")["code"]
        self.assertEqual(self.accept(self.child, code).status_code, 400)

        # Teskari yo'nalish: farzand ota-onaning ota-onasi bo'lmoqchi
        User.objects.filter(pk=self.child.pk).update(
            email="bola@example.com", email_verified_at=timezone.now()
        )
        self.child.refresh_from_db()
        child_code = self.make_invite(self.child, "parent")
        self.assertEqual(self.accept(self.parent, child_code["code"]).status_code, 400)
        self.assertEqual(ParentChildLink.objects.count(), 1)

    def test_accept_is_throttled(self):
        for _ in range(10):
            self.accept(self.stranger, "AAAAAAAA")
        self.assertEqual(self.accept(self.stranger, "AAAAAAAA").status_code, 429)

    def test_requires_login(self):
        self.assertEqual(
            APIClient().post(reverse("family-accept"), {"code": "AAAAAAAA"}).status_code,
            403,
        )


class LinkTests(FamilyTestCase):
    def test_both_sides_see_link_without_contacts(self):
        self.link()

        parent_view = self.client_for(self.parent).get(reverse("family-link-list")).json()
        child_view = self.client_for(self.child).get(reverse("family-link-list")).json()

        self.assertEqual(parent_view[0]["relation"], "child")
        self.assertEqual(parent_view[0]["user"]["username"], "bola")
        self.assertEqual(child_view[0]["relation"], "parent")
        self.assertEqual(child_view[0]["user"]["username"], "ota")
        for entry in parent_view + child_view:
            self.assertNotIn("email", entry["user"])
            self.assertNotIn("phone", entry["user"])

    def test_stranger_sees_nothing_and_cannot_unlink(self):
        link = self.link()
        client = self.client_for(self.stranger)

        self.assertEqual(client.get(reverse("family-link-list")).json(), [])
        response = client.delete(reverse("family-link-detail", args=[link.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(ParentChildLink.objects.get().revoked_at)

    def test_either_side_can_unlink(self):
        for actor in (self.parent, self.child):
            link = self.link()
            response = self.client_for(actor).delete(
                reverse("family-link-detail", args=[link.pk])
            )
            self.assertEqual(response.status_code, 204)
            link.refresh_from_db()
            self.assertEqual(link.revoked_by, actor)
            self.assertFalse(is_parent_of(self.parent, self.child))
            ParentChildLink.objects.all().delete()
            FamilyInvite.objects.all().delete()
        self.assertTrue(AuditLog.objects.filter(action="family.unlinked").exists())

    def test_can_relink_after_unlink(self):
        link = self.link()
        self.client_for(self.parent).delete(reverse("family-link-detail", args=[link.pk]))
        code = self.make_invite(self.parent, "parent")["code"]
        self.assertEqual(self.accept(self.child, code).status_code, 201)
        self.assertEqual(ParentChildLink.objects.filter(revoked_at__isnull=True).count(), 1)


class ServiceHelperTests(FamilyTestCase):
    def test_access_helpers(self):
        self.assertFalse(is_parent_of(self.parent, self.child))
        self.link()

        self.assertTrue(is_parent_of(self.parent, self.child))
        self.assertFalse(is_parent_of(self.child, self.parent))  # teskarisi emas
        self.assertFalse(is_parent_of(self.stranger, self.child))
        self.assertEqual(list(children_of(self.parent)), [self.child.pk])
        self.assertEqual(list(parents_of(self.child)), [self.parent.pk])
        self.assertEqual(list(children_of(self.stranger)), [])


class ConstraintTests(FamilyTestCase):
    def test_database_blocks_self_link_and_duplicates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParentChildLink.objects.create(parent=self.parent, child=self.parent)
        ParentChildLink.objects.create(parent=self.parent, child=self.child)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParentChildLink.objects.create(parent=self.parent, child=self.child)
