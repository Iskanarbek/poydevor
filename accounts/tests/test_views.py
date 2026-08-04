from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class SignupViewTests(TestCase):
    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "Aziz", "last_name": "Karimov",
            "phone": "+998901112233", "password": "testpass123",
            "role": User.Role.USER,
        })
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(phone="+998901112233")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_duplicate_phone_shows_error(self):
        User.objects.create_user(
            phone="+998901112233", password="x",
            first_name="A", last_name="B", role=User.Role.USER,
        )
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "C", "last_name": "D",
            "phone": "+998901112233", "password": "testpass123",
            "role": User.Role.USER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "band")  # "band" = "taken" in Uzbek error copy

    def test_signup_rejects_weak_password(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "Aziz", "last_name": "Karimov",
            "phone": "+998901112233", "password": "12345678",
            "role": User.Role.USER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertTrue(response.context["form"].errors.get("password"))

    def test_signup_requires_first_and_last_name(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "", "last_name": "",
            "phone": "+998901112233", "password": "testpass123",
            "role": User.Role.USER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertTrue(response.context["form"].errors.get("first_name"))
        self.assertTrue(response.context["form"].errors.get("last_name"))


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901112233", password="testpass123",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )

    def test_login_with_correct_credentials(self):
        response = self.client.post(reverse("accounts:login"), {
            "phone": "+998901112233", "password": "testpass123",
        })
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(reverse("accounts:login"), {
            "phone": "+998901112233", "password": "wrong",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
