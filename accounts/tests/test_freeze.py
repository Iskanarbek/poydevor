from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.services import freeze_account, unfreeze_account


def make_staff():
    return User.objects.create_superuser(phone="+998900000001", password="x", first_name="Admin", last_name="A")


def make_user():
    return User.objects.create_user(
        phone="+998901111111", password="x", first_name="Ali", last_name="V", role=User.Role.USER,
    )


class FreezeServiceTests(TestCase):
    def test_freeze_deactivates_and_records_reason(self):
        user = make_user()
        freeze_account(user, "shubhali faoliyat")
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.frozen_reason, "shubhali faoliyat")
        self.assertIsNotNone(user.frozen_at)

    def test_unfreeze_reactivates_and_clears_reason(self):
        user = make_user()
        freeze_account(user, "test")
        unfreeze_account(user)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.frozen_reason, "")
        self.assertIsNone(user.frozen_at)

    def test_a_frozen_user_cannot_log_in(self):
        user = make_user()
        user.set_password("secret123")
        user.save()
        freeze_account(user)
        self.assertFalse(self.client.login(phone=user.phone, password="secret123"))


class FreezeAdminViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.target = make_user()
        self.client.force_login(self.staff)

    def test_freeze_confirm_page_loads(self):
        page = self.client.get(reverse("admin:accounts_user_freeze", args=[self.target.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Hisobni muzlatasizmi?")

    def test_posting_freeze_form_freezes_with_reason(self):
        response = self.client.post(
            reverse("admin:accounts_user_freeze", args=[self.target.pk]), {"reason": "firibgarlik shubhasi"},
        )
        self.assertRedirects(response, reverse("admin:accounts_user_changelist"))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.target.frozen_reason, "firibgarlik shubhasi")

    def test_posting_unfreeze_reactivates(self):
        freeze_account(self.target, "test")
        response = self.client.post(reverse("admin:accounts_user_unfreeze", args=[self.target.pk]))
        self.assertRedirects(response, reverse("admin:accounts_user_changelist"))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_changelist_shows_status_and_action_link(self):
        page = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertContains(page, "Faol")
        self.assertContains(page, reverse("admin:accounts_user_freeze", args=[self.target.pk]))

    def test_non_staff_cannot_freeze_anyone(self):
        self.client.logout()
        other = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Boshqa", last_name="K", role=User.Role.USER,
        )
        self.client.force_login(other)
        response = self.client.get(reverse("admin:accounts_user_freeze", args=[self.target.pk]))
        self.assertNotEqual(response.status_code, 200)
