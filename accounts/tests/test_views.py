from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from accounts.models import User
from accounts.phone import InvalidPhoneError, normalize_phone


class PhoneNormalizationTests(TestCase):
    def test_accepts_common_formats(self):
        for raw in ["+998901234567", "998901234567", "90 123 45 67", "+998 (90) 123-45-67", "901234567"]:
            self.assertEqual(normalize_phone(raw), "+998901234567", raw)

    def test_rejects_garbage(self):
        for raw in ["", "12345", "+1 202 555 0100", "abc"]:
            with self.assertRaises(InvalidPhoneError):
                normalize_phone(raw)


class SignupViewTests(TestCase):
    def test_signup_creates_passwordless_client_and_logs_in(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "Aziz", "last_name": "Karimov", "phone": "90 111 22 33",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(phone="+998901112233")
        self.assertEqual(user.role, User.Role.USER)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_duplicate_phone_shows_error(self):
        User.objects.create_user(
            phone="+998901112233", first_name="A", last_name="B", role=User.Role.USER,
        )
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "C", "last_name": "D", "phone": "+998 90 111 22 33",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, escape("allaqachon ro'yxatdan o'tgan"))
        self.assertEqual(User.objects.count(), 1)

    def test_signup_requires_first_and_last_name(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "", "last_name": "", "phone": "+998901112233",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertTrue(response.context["form"].errors.get("first_name"))
        self.assertTrue(response.context["form"].errors.get("last_name"))

    def test_signup_rejects_invalid_phone(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "Aziz", "last_name": "Karimov", "phone": "12345",
        })
        self.assertEqual(User.objects.count(), 0)
        self.assertTrue(response.context["form"].errors.get("phone"))


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901112233", first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )

    def test_login_with_phone_only(self):
        response = self.client.post(reverse("accounts:login"), {"phone": "+998901112233"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_accepts_differently_formatted_phone(self):
        self.client.post(reverse("accounts:login"), {"phone": "90 111 22 33"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_account_stored_in_an_old_phone_format_can_still_log_in(self):
        legacy = User.objects.create_user(phone="9354011155", first_name="Old", last_name="Account", role=User.Role.USER)
        response = self.client.post(reverse("accounts:login"), {"phone": "9354011155"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), legacy.pk)

    def test_login_with_unknown_phone_fails(self):
        response = self.client.post(reverse("accounts:login"), {"phone": "+998909999999"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_cannot_log_in_with_phone_only(self):
        User.objects.create_superuser(phone="+998900000001", password="secret-pass-1", first_name="A", last_name="D")
        response = self.client.post(reverse("accounts:login"), {"phone": "+998900000001"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_can_still_log_in_with_password(self):
        User.objects.create_superuser(phone="+998900000001", password="secret-pass-1", first_name="A", last_name="D")
        self.assertTrue(self.client.login(phone="+998900000001", password="secret-pass-1"))


class WelcomeAndHomeViewTests(TestCase):
    def test_anonymous_visitor_redirected_to_welcome(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:welcome"))

    def test_welcome_offers_client_and_architect_paths(self):
        response = self.client.get(reverse("accounts:welcome"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, escape(reverse("accounts:signup")))
        self.assertContains(response, reverse("architects:select_type"))

    def test_authenticated_user_redirected_to_dashboard(self):
        user = User.objects.create_user(
            phone="+998901112233", first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_architect_list_still_resolves_and_is_not_shadowed(self):
        response = self.client.get("/arxitektorlar/")
        self.assertEqual(response.status_code, 200)


class LogoutConfirmationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901112233", first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_opening_the_logout_link_only_asks_for_confirmation(self):
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hisobdan chiqasizmi?")
        self.assertContains(response, "Bekor qilish")
        # Still signed in: a plain link or a page pre-fetch can't log anyone out.
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_confirming_logs_out(self):
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:welcome"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_needs_a_csrf_token(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(reverse("accounts:logout")).status_code, 403)
        self.assertIn("_auth_user_id", strict.session)

    def test_anonymous_visitor_is_sent_to_welcome(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:welcome"), fetch_redirect_response=False)
