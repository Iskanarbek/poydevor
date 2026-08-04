from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application


class PostApplicationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_post_application_known_size(self):
        response = self.client.post(reverse("applications:post"), {
            "size_unknown": "", "size_m2": 100, "rooms_count": 3,
            "location": "Toshkent", "budget": "", "interior_style": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Application.objects.count(), 1)

    def test_post_application_unknown_size(self):
        response = self.client.post(reverse("applications:post"), {
            "size_unknown": "on", "size_m2": "", "rooms_count": 5,
            "location": "Buxoro", "budget": "", "interior_style": "",
        })
        self.assertEqual(response.status_code, 302)
        app = Application.objects.get()
        self.assertIsNone(app.size_m2)


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_dashboard_lists_own_applications(self):
        Application.objects.create(owner=self.user, rooms_count=2, location="Andijon")
        response = self.client.get(reverse("applications:dashboard"))
        self.assertContains(response, "Andijon")


class DeleteApplicationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.other_user = User.objects.create_user(
            phone="+998907654321", password="x",
            first_name="Malika", last_name="Rashidova", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_owner_can_delete_open_application(self):
        application = Application.objects.create(
            owner=self.user, rooms_count=2, location="Andijon", status=Application.Status.OPEN,
        )
        response = self.client.post(reverse("applications:delete", args=[application.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Application.objects.filter(pk=application.pk).exists())

    def test_non_owner_cannot_delete_application(self):
        application = Application.objects.create(
            owner=self.other_user, rooms_count=2, location="Buxoro", status=Application.Status.OPEN,
        )
        response = self.client.post(reverse("applications:delete", args=[application.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Application.objects.filter(pk=application.pk).exists())

    def test_non_open_application_cannot_be_deleted(self):
        application = Application.objects.create(
            owner=self.user, rooms_count=2, location="Xiva", status=Application.Status.IN_PROGRESS,
        )
        response = self.client.post(reverse("applications:delete", args=[application.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Application.objects.filter(pk=application.pk).exists())
