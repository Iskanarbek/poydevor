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
