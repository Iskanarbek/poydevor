from django.test import TestCase

from accounts.models import User
from applications.models import Application


class ApplicationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )

    def test_create_application_with_known_size(self):
        app = Application.objects.create(
            owner=self.user, size_m2=120, rooms_count=4, location="Toshkent",
        )
        self.assertEqual(app.status, Application.Status.OPEN)
        self.assertIsNotNone(app.size_m2)

    def test_create_application_with_unknown_size(self):
        app = Application.objects.create(
            owner=self.user, size_m2=None, rooms_count=3, location="Samarqand",
        )
        self.assertIsNone(app.size_m2)
