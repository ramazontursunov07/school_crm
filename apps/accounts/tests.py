from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def create_user(self, username, **fields):
        return User.objects.create_user(username=username, **fields)

    def test_password_is_hashed(self):
        user = self.create_user("ali", password="Test-parol-12345")

        self.assertNotEqual(user.password, "Test-parol-12345")
        self.assertTrue(user.check_password("Test-parol-12345"))

    def test_contacts_are_normalized(self):
        user = self.create_user(
            "ali", email="  Ali@Example.COM ", phone=" +998901234567 "
        )
        user.refresh_from_db()

        self.assertEqual(user.email, "ali@example.com")
        self.assertEqual(user.phone, "+998901234567")

    def test_many_users_may_have_empty_contacts(self):
        first = self.create_user("ali", email="", phone="")
        second = self.create_user("vali", email="", phone="")

        for user in (first, second):
            user.refresh_from_db()
            self.assertIsNone(user.email)
            self.assertIsNone(user.phone)

    def test_email_is_unique_ignoring_case(self):
        self.create_user("ali", email="ali@example.com")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_user("vali", email="ALI@example.com")

    def test_phone_is_unique(self):
        self.create_user("ali", phone="+998901234567")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_user("vali", phone="+998901234567")