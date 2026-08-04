from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from offers.services import (
    MaxArchitectsReachedError,
    accept_offer,
    complete_offer,
    reject_offer,
    send_offer,
)
from wallet.models import Wallet
from wallet.services import InsufficientCoinsError, topup_coins


class SendOfferTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        self.architects = []
        for i in range(4):
            u = User.objects.create_user(
                phone=f"+99890000000{i}", password="x", first_name=f"Arx{i}", last_name="Y", role=User.Role.ARCHITECT,
            )
            profile = ArchitectProfile.objects.create(user=u, bio="x")
            wallet = Wallet.objects.create(architect=profile)
            topup_coins(wallet, 100)
            self.architects.append(profile)

    def test_architect_applied_spends_20_coins(self):
        offer = send_offer(self.application, self.architects[0], source=Offer.Source.ARCHITECT_APPLIED)
        self.architects[0].wallet.refresh_from_db()
        self.assertEqual(self.architects[0].wallet.balance, 80)
        self.assertEqual(offer.status, Offer.Status.PENDING)

    def test_fourth_architect_applied_offer_blocked(self):
        for profile in self.architects[:3]:
            send_offer(self.application, profile, source=Offer.Source.ARCHITECT_APPLIED)
        with self.assertRaises(MaxArchitectsReachedError):
            send_offer(self.application, self.architects[3], source=Offer.Source.ARCHITECT_APPLIED)
        self.architects[3].wallet.refresh_from_db()
        self.assertEqual(self.architects[3].wallet.balance, 100)  # not charged

    def test_insufficient_coins_blocks_offer(self):
        u = User.objects.create_user(
            phone="+998909999999", password="x", first_name="Poor", last_name="Y", role=User.Role.ARCHITECT,
        )
        poor_profile = ArchitectProfile.objects.create(user=u, bio="x")
        Wallet.objects.create(architect=poor_profile)  # balance 0
        with self.assertRaises(InsufficientCoinsError):
            send_offer(self.application, poor_profile, source=Offer.Source.ARCHITECT_APPLIED)

    def test_user_invited_offer_does_not_spend_coins(self):
        offer = send_offer(self.application, self.architects[0], source=Offer.Source.USER_INVITED)
        self.architects[0].wallet.refresh_from_db()
        self.assertEqual(self.architects[0].wallet.balance, 100)
        self.assertEqual(offer.source, Offer.Source.USER_INVITED)


class AcceptRejectOfferTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        self.offers = []
        for i in range(3):
            u = User.objects.create_user(
                phone=f"+99890000000{i}", password="x", first_name=f"Arx{i}", last_name="Y", role=User.Role.ARCHITECT,
            )
            profile = ArchitectProfile.objects.create(user=u, bio="x")
            Wallet.objects.create(architect=profile, balance=100)
            self.offers.append(
                Offer.objects.create(application=self.application, architect=profile, source=Offer.Source.ARCHITECT_APPLIED)
            )

    def test_accept_rejects_siblings_and_moves_application_in_progress(self):
        accept_offer(self.offers[0])
        self.application.refresh_from_db()
        self.offers[1].refresh_from_db()
        self.offers[2].refresh_from_db()
        self.offers[0].refresh_from_db()

        self.assertEqual(self.offers[0].status, Offer.Status.ACCEPTED)
        self.assertEqual(self.offers[1].status, Offer.Status.REJECTED)
        self.assertEqual(self.offers[2].status, Offer.Status.REJECTED)
        self.assertEqual(self.application.status, Application.Status.IN_PROGRESS)

    def test_reject_single_offer_leaves_others_pending(self):
        reject_offer(self.offers[0])
        self.offers[1].refresh_from_db()
        self.assertEqual(self.offers[0].status, Offer.Status.REJECTED)
        self.assertEqual(self.offers[1].status, Offer.Status.PENDING)

    def test_complete_offer_updates_counts_and_application(self):
        accept_offer(self.offers[0])
        complete_offer(self.offers[0])
        self.offers[0].refresh_from_db()
        self.application.refresh_from_db()
        self.offers[0].architect.refresh_from_db()

        self.assertEqual(self.offers[0].status, Offer.Status.COMPLETED)
        self.assertEqual(self.application.status, Application.Status.CLOSED)
        self.assertEqual(self.offers[0].architect.completed_projects_count, 1)
