from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile

Approval = ArchitectProfile.ApprovalStatus
Verification = ArchitectProfile.VerificationStatus


def make_staff(password="staffpass123"):
    user = User.objects.create_superuser(phone="+998900000001", password=password, first_name="Admin", last_name="A")
    return user


def make_architect(name="Botir", phone="+998901111111", verification=Verification.PENDING, kind=ArchitectProfile.Kind.FREELANCER):
    user = User.objects.create_user(phone=phone, first_name=name, last_name="X", role=User.Role.ARCHITECT)
    return ArchitectProfile.objects.create(user=user, kind=kind, portfolio_verification=verification)


class StaffLoginTests(TestCase):
    def test_wrong_password_is_rejected(self):
        make_staff(password="correct-pass")
        response = self.client.post(reverse("staff_login"), {"username": "+998900000001", "password": "wrong"})
        self.assertEqual(response.status_code, 200)  # re-renders the form with an error
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_correct_password_logs_a_staff_member_in(self):
        make_staff(password="correct-pass")
        response = self.client.post(reverse("staff_login"), {"username": "+998900000001", "password": "correct-pass"})
        self.assertRedirects(response, reverse("staff_home"))

    def test_a_non_staff_user_with_a_password_is_refused(self):
        user = User.objects.create_user(phone="+998902222222", password="somepass", first_name="A", last_name="B", role=User.Role.USER)
        response = self.client.post(reverse("staff_login"), {"username": user.phone, "password": "somepass"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin panelga kirish huquqi yo")

    def test_ordinary_passwordless_login_cannot_reach_a_staff_account(self):
        """The normal client/architect login (phone only, no password) must
        never authenticate a staff account — that's the whole point of
        having a separate staff login."""
        make_staff(password="correct-pass")
        response = self.client.post(reverse("accounts:login"), {"phone": "+998900000001"})
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class StaffPanelAccessTests(TestCase):
    def test_anonymous_is_redirected_to_staff_login(self):
        response = self.client.get(reverse("staff_home"))
        self.assertRedirects(response, f"{reverse('staff_login')}?next={reverse('staff_home')}")

    def test_an_ordinary_logged_in_user_is_also_redirected(self):
        user = User.objects.create_user(phone="+998903333333", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_home"))
        self.assertRedirects(response, f"{reverse('staff_login')}?next={reverse('staff_home')}")

    def test_staff_can_reach_the_home_page(self):
        staff = make_staff()
        self.client.force_login(staff)
        response = self.client.get(reverse("staff_home"))
        self.assertEqual(response.status_code, 200)


class ArchitectsListTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.client.force_login(self.staff)

    def test_lists_architects(self):
        make_architect(name="Dilnoza")
        page = self.client.get(reverse("staff_architects_list"))
        self.assertContains(page, "Dilnoza")

    def test_search_by_phone(self):
        make_architect(name="Dilnoza", phone="+998907654321")
        make_architect(name="Sardor", phone="+998909999999")
        page = self.client.get(reverse("staff_architects_list"), {"q": "7654321"})
        self.assertContains(page, "Dilnoza")
        self.assertNotContains(page, "Sardor")

    def test_search_by_name(self):
        make_architect(name="Dilnoza", phone="+998907654321")
        make_architect(name="Sardor", phone="+998909999999")
        page = self.client.get(reverse("staff_architects_list"), {"q": "sardor"})
        self.assertContains(page, "Sardor")
        self.assertNotContains(page, "Dilnoza")

    def test_filter_by_verification_status(self):
        make_architect(name="Kutayotgan", verification=Verification.PENDING)
        make_architect(name="Tasdiqlangan", phone="+998908888888", verification=Verification.VERIFIED)
        page = self.client.get(reverse("staff_architects_list"), {"verification": "verified"})
        self.assertContains(page, "Tasdiqlangan")
        self.assertNotContains(page, "Kutayotgan")


class ArchitectDetailActionTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.client.force_login(self.staff)
        self.profile = make_architect(verification=Verification.PENDING)

    def test_detail_page_loads(self):
        page = self.client.get(reverse("staff_architect_detail", args=[self.profile.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.profile.user.phone)

    def test_verify_action(self):
        response = self.client.post(reverse("staff_architect_verify", args=[self.profile.pk]))
        self.assertRedirects(response, reverse("staff_architect_detail", args=[self.profile.pk]))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.portfolio_verification, Verification.VERIFIED)

    def test_reject_action_with_note(self):
        response = self.client.post(
            reverse("staff_architect_reject", args=[self.profile.pk]), {"note": "sifatsiz suratlar"},
        )
        self.assertRedirects(response, reverse("staff_architect_detail", args=[self.profile.pk]))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.portfolio_verification, Verification.REJECTED)
        self.assertEqual(self.profile.verification_note, "sifatsiz suratlar")

    def test_non_staff_gets_redirected_not_shown_the_page(self):
        self.client.logout()
        user = User.objects.create_user(phone="+998904444444", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_architect_detail", args=[self.profile.pk]))
        self.assertRedirects(response, f"{reverse('staff_login')}?next={reverse('staff_architect_detail', args=[self.profile.pk])}")
