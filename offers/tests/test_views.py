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
        self.assertEqual(self.architect.wallet.balance, 90)


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


class OfferAcceptRaceTests(TestCase):
    """Two architects hold pending offers on the same application. A
    concurrent request accepts offer_1 first, which (atomically) flips the
    application out of OPEN. offer_2 is still PENDING when the second
    request reaches the view, so accept_offer(offer_2) finds zero rows to
    update on the OPEN-status filter and raises OfferAlreadyDecidedError.
    The view must redirect, not surface that as an unhandled 500.

    We reproduce the "application already moved on" half of the race
    directly (rather than routing through accept_offer(offer_1), which
    would also auto-reject offer_2 and mask the bug behind a 404 instead
    of the unhandled-exception path this test targets)."""

    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")

        architect_user_1 = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect_1 = ArchitectProfile.objects.create(user=architect_user_1, bio="x")
        self.offer_1 = Offer.objects.create(
            application=self.application, architect=self.architect_1, source=Offer.Source.USER_INVITED,
        )

        architect_user_2 = User.objects.create_user(
            phone="+998903333333", password="x", first_name="Malika", last_name="R", role=User.Role.ARCHITECT,
        )
        self.architect_2 = ArchitectProfile.objects.create(user=architect_user_2, bio="y")
        self.offer_2 = Offer.objects.create(
            application=self.application, architect=self.architect_2, source=Offer.Source.USER_INVITED,
        )

        self.owner = owner
        self.architect_user_2 = architect_user_2

        # Simulate the winning half of the race: the application has
        # already moved out of OPEN (as accept_offer would leave it), but
        # offer_2 itself is untouched and still PENDING.
        Application.objects.filter(pk=self.application.pk).update(status=Application.Status.IN_PROGRESS)

    def test_respond_accept_after_race_redirects_not_500(self):
        self.client.force_login(self.architect_user_2)
        response = self.client.post(
            reverse("offers:respond", args=[self.offer_2.pk]), {"decision": "accept"},
        )
        self.assertEqual(response.status_code, 302)
        self.offer_2.refresh_from_db()
        self.assertEqual(self.offer_2.status, Offer.Status.PENDING)

    def test_user_respond_accept_after_race_redirects_not_500(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("offers:user_respond", args=[self.offer_2.pk]), {"decision": "accept"},
        )
        self.assertEqual(response.status_code, 302)
        self.offer_2.refresh_from_db()
        self.assertEqual(self.offer_2.status, Offer.Status.PENDING)


class ArchitectProjectDetailTests(TestCase):
    """The market card -> detail page -> take-the-project flow."""

    def setUp(self):
        from architects.models import Style
        self.owner = User.objects.create_user(
            phone="+998901111111", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(
            owner=self.owner, size_m2=180, rooms_count=5, location="Toshkent, Chilonzor",
            interior_style=Style.objects.create(name="Xay-tek"), budget=250_000_000,
            description="Ikki qavatli hi-tech uy loyihasi va interyer dizayni kerak.",
        )
        architect_user = User.objects.create_user(
            phone="+998902222222", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.architect, balance=20)
        self.client.force_login(architect_user)
        self.url = reverse("offers:architect_apply", args=[self.application.pk])

    def test_market_card_shows_what_an_architect_needs_to_assess_the_project(self):
        response = self.client.get("/freelancer/dashboard/?tab=market")
        for expected in ("Toshkent, Chilonzor", "180 m²", "5 xona", "Xay-tek", "250", "hi-tech uy loyihasi", "Ko'rish"):
            self.assertContains(response, expected)
        self.assertNotContains(response, "Tez orada")

    def test_detail_page_shows_full_information_and_take_button(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Ikki qavatli hi-tech uy loyihasi")
        self.assertContains(response, "Qatnashish — 10 tanga")
        self.assertEqual((response.context["can_afford"], response.context["balance_after"]), (True, 10))
        # The client's contact details stay hidden until the offer is accepted.
        self.assertNotContains(response, self.owner.phone)

    def test_taking_the_project_spends_ten_coins(self):
        self.client.post(self.url)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 10)
        self.assertTrue(Offer.objects.filter(application=self.application, architect=self.architect).exists())

    def test_two_projects_fit_the_starting_coins_and_a_third_is_blocked(self):
        second = Application.objects.create(owner=self.owner, rooms_count=3, location="Samarqand")
        third = Application.objects.create(owner=self.owner, rooms_count=2, location="Buxoro")
        self.client.post(self.url)
        self.client.post(reverse("offers:architect_apply", args=[second.pk]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)

        page = self.client.get(reverse("offers:architect_apply", args=[third.pk]))
        self.assertContains(page, "Tangalar yetarli emas")
        self.assertNotContains(page, "Qatnashish — 10 tanga")
        self.assertFalse(page.context["can_afford"])

        # Even a forged POST can't take it without coins.
        forged = self.client.post(reverse("offers:architect_apply", args=[third.pk]))
        self.assertContains(forged, "Tangalar yetarli emas")
        self.assertFalse(Offer.objects.filter(application=third).exists())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)

    def test_already_applied_and_full_states(self):
        self.client.post(self.url)
        page = self.client.get(self.url)
        self.assertContains(page, "ariza yuborgansiz")
        self.assertNotContains(page, "Qatnashish — 10 tanga")

        other = Application.objects.create(owner=self.owner, rooms_count=3, location="Namangan")
        for i in range(3):
            u = User.objects.create_user(phone=f"+99890333000{i}", first_name="X", last_name="Y", role=User.Role.ARCHITECT)
            p = ArchitectProfile.objects.create(user=u, bio="x")
            Offer.objects.create(application=other, architect=p, source=Offer.Source.USER_INVITED)
        full = self.client.get(reverse("offers:architect_apply", args=[other.pk]))
        self.assertContains(full, "Barcha joylar band")
        self.assertTrue(full.context["is_full"])

    def test_pending_architect_cannot_open_the_detail_page(self):
        self.architect.approval_status = ArchitectProfile.ApprovalStatus.PENDING
        self.architect.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
