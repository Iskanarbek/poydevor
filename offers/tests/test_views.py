from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from wallet.models import Wallet


class SendOfferFromArchitectProfileTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        self.client.force_login(self.owner)

    def test_user_sends_offer_to_architect(self):
        response = self.client.post(
            reverse("offers:send", args=[self.architect.pk]), {"application": self.application.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Offer.objects.filter(application=self.application, architect=self.architect).exists())


class ArchitectApplyTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        Wallet.objects.create(architect=self.architect, balance=100)
        self.client.force_login(architect_user)

    def test_get_does_not_create_offer_or_spend_coins(self):
        response = self.client.get(reverse("offers:architect_apply", args=[self.application.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Offer.objects.filter(application=self.application, architect=self.architect).exists())
        self.architect.wallet.refresh_from_db()
        self.assertEqual(self.architect.wallet.balance, 100)

    def test_post_creates_offer_and_spends_coins(self):
        response = self.client.post(reverse("offers:architect_apply", args=[self.application.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Offer.objects.filter(application=self.application, architect=self.architect).exists())
        self.architect.wallet.refresh_from_db()
        self.assertEqual(self.architect.wallet.balance, 80)


class ArchitectRespondTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        Wallet.objects.create(architect=self.architect, balance=100)
        self.offer = Offer.objects.create(
            application=self.application, architect=self.architect, source=Offer.Source.USER_INVITED,
        )
        self.client.force_login(architect_user)

    def test_architect_accepts_offer(self):
        response = self.client.post(reverse("offers:respond", args=[self.offer.pk]), {"decision": "accept"})
        self.assertEqual(response.status_code, 302)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, Offer.Status.ACCEPTED)

    def test_architect_rejects_offer(self):
        response = self.client.post(reverse("offers:respond", args=[self.offer.pk]), {"decision": "reject"})
        self.assertEqual(response.status_code, 302)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, Offer.Status.REJECTED)
