from django.test import TestCase
from accounts.models import User


class UserModelTests(TestCase):
    def test_create_user_with_phone(self):
        user = User.objects.create_user(
            phone="+998901234567", password="testpass123",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.assertEqual(user.phone, "+998901234567")
        self.assertTrue(user.check_password("testpass123"))
        self.assertEqual(user.role, User.Role.USER)

    def test_phone_is_unique(self):
        User.objects.create_user(
            phone="+998901234567", password="pass1",
            first_name="A", last_name="B", role=User.Role.USER,
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                phone="+998901234567", password="pass2",
                first_name="C", last_name="D", role=User.Role.ARCHITECT,
            )

    def test_role_choices(self):
        self.assertEqual(User.Role.USER, "user")
        self.assertEqual(User.Role.ARCHITECT, "architect")
