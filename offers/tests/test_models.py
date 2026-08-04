from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer


class OfferModelTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")

    def test_create_pending_offer(self):
        offer = Offer.objects.create(
            application=self.application, architect=self.architect,
            source=Offer.Source.ARCHITECT_APPLIED,
        )
        self.assertEqual(offer.status, Offer.Status.PENDING)
