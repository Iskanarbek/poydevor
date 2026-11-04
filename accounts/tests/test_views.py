from django.test import TestCase, override_settings
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


# --- switching accounts, redirects and error pages ---

class SwitchingAccountsTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            phone="+998901111111", first_name="Mijoz", last_name="Bir", role=User.Role.USER,
        )
        self.other = User.objects.create_user(
            phone="+998902222222", first_name="Mijoz", last_name="Ikki", role=User.Role.USER,
        )

    def log_in(self, phone, **extra):
        return self.client.post(reverse("accounts:login"), {"phone": phone, **extra})

    def test_login_goes_where_the_visitor_was_heading(self):
        target = reverse("applications:dashboard")
        response = self.client.get(target)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={target}", fetch_redirect_response=False)
        page = self.client.get(response.url)
        self.assertContains(page, f'name="next" value="{target}"')
        self.assertRedirects(self.log_in("+998901111111", next=target), target, fetch_redirect_response=False)

    def test_login_never_follows_an_address_outside_the_site(self):
        for bad in ("https://evil.example/", "//evil.example/", "javascript:alert(1)"):
            with self.subTest(next=bad):
                self.client.logout()
                self.assertRedirects(self.log_in("+998901111111", next=bad), reverse("dashboard"), fetch_redirect_response=False)

    def test_logout_then_login_as_someone_else_lands_on_their_own_page(self):
        self.log_in("+998901111111")
        self.client.post(reverse("accounts:logout"))
        self.assertRedirects(self.client.get(reverse("applications:dashboard")), f"{reverse('accounts:login')}?next={reverse('applications:dashboard')}", fetch_redirect_response=False)
        self.log_in("+998902222222")
        page = self.client.get(reverse("applications:dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.other.pk)

    def test_the_login_screen_does_not_show_for_someone_already_signed_in(self):
        self.log_in("+998901111111")
        self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("dashboard"), fetch_redirect_response=False)

    def test_pages_are_never_cached_by_the_browser(self):
        self.log_in("+998901111111")
        for url in (reverse("applications:dashboard"), reverse("accounts:welcome"), reverse("dashboard")):
            with self.subTest(url=url):
                self.assertIn("no-store", self.client.get(url)["Cache-Control"])

    def test_static_files_stay_cacheable(self):
        from poydevor.middleware import NoStorePagesMiddleware
        from django.http import HttpResponse
        from django.test import RequestFactory
        middleware = NoStorePagesMiddleware(lambda request: HttpResponse("x"))
        self.assertFalse(middleware(RequestFactory().get("/static/a.css")).has_header("Cache-Control"))
        self.assertFalse(middleware(RequestFactory().get("/media/a.jpg")).has_header("Cache-Control"))

    def test_flash_messages_do_not_travel_to_the_next_account(self):
        from django.conf import settings
        self.assertIn("session", settings.MESSAGE_STORAGE)


class ErrorPagesTests(TestCase):
    def test_unknown_address_shows_our_own_404_with_a_way_back(self):
        response = self.client.get("/bunday-sahifa-yoq/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "errors/404.html")
        self.assertContains(response, "Sahifa topilmadi", status_code=404)
        self.assertContains(response, 'href="/welcome/"', status_code=404)

    def test_a_stale_form_after_switching_accounts_gets_a_friendly_page_not_a_bare_403(self):
        client = self.client_class(enforce_csrf_checks=True)
        response = client.post(reverse("accounts:login"), {"phone": "+998901111111"})
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Sessiya yangilandi", status_code=403)
        self.assertContains(response, 'href="/welcome/"', status_code=403)

    def test_500_page_stands_alone_and_links_home(self):
        from django.template import loader
        html = loader.get_template("errors/500.html").render({})
        self.assertIn('href="/welcome/"', html)


class ArchitectPasswordTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(phone="+998901111111", first_name="M", last_name="B", role=User.Role.USER)
        self.arch = User.objects.create_user(phone="+998902222222", first_name="A", last_name="R", role=User.Role.ARCHITECT)
        self.arch.set_password("1")
        self.arch.save()

    def login(self, phone, password=""):
        return self.client.post(reverse("accounts:login"), {"phone": phone, "password": password})

    def test_an_architect_needs_the_right_password(self):
        self.assertEqual(self.login("+998902222222").status_code, 200)
        self.assertEqual(self.login("+998902222222", "2").status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.login("+998902222222", "1").status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.arch.pk)

    def test_a_client_still_signs_in_with_the_phone_alone(self):
        self.assertEqual(self.login("+998901111111").status_code, 302)

    def test_any_password_is_allowed_even_one_character(self):
        from accounts.forms import SetPasswordForm
        self.assertTrue(SetPasswordForm({"password": "1", "password_confirm": "1"}).is_valid())
        self.assertFalse(SetPasswordForm({"password": "1", "password_confirm": "2"}).is_valid())

    @override_settings(REQUIRE_ARCHITECT_PASSWORD=True)
    def test_an_old_architect_without_a_password_must_create_one_first(self):
        old = User.objects.create_user(phone="+998903333333", first_name="O", last_name="D", role=User.Role.ARCHITECT)
        self.assertFalse(old.has_usable_password())
        self.assertEqual(self.login("+998903333333").status_code, 302)          # may still get in...
        self.assertRedirects(self.client.get(reverse("applications:dashboard")), reverse("accounts:set_password"), fetch_redirect_response=False)
        self.client.post(reverse("accounts:set_password"), {"password": "x", "password_confirm": "x"})
        old.refresh_from_db()
        self.assertTrue(old.check_password("x"))
        self.assertEqual(self.client.get(reverse("accounts:set_password")).status_code, 200)   # still signed in
        self.assertNotEqual(self.client.get(reverse("applications:dashboard")).url if self.client.get(reverse("applications:dashboard")).status_code == 302 else "", reverse("accounts:set_password"))
