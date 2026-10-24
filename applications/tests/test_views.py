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

    def test_delete_link_asks_for_confirmation_first(self):
        application = Application.objects.create(owner=self.user, rooms_count=2, location="Andijon")
        response = self.client.get(reverse("applications:delete", args=[application.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E'lonni o'chirasizmi?")
        application.refresh_from_db()
        self.assertIsNone(application.deleted_at)  # opening the page deletes nothing

    def test_owner_can_delete_open_application(self):
        application = Application.objects.create(owner=self.user, rooms_count=2, location="Andijon")
        response = self.client.post(reverse("applications:delete", args=[application.pk]))
        self.assertRedirects(response, reverse("applications:dashboard"), fetch_redirect_response=False)
        application.refresh_from_db()
        self.assertIsNotNone(application.deleted_at)
        self.assertNotContains(self.client.get(reverse("applications:dashboard")), "Andijon")
        self.assertEqual(self.client.get(reverse("applications:detail", args=[application.pk])).status_code, 404)

    def test_owner_can_delete_orders_in_any_status(self):
        for status in (Application.Status.IN_PROGRESS, Application.Status.CLOSED):
            with self.subTest(status=status):
                application = Application.objects.create(owner=self.user, rooms_count=2, location="Xiva", status=status)
                self.client.post(reverse("applications:delete", args=[application.pk]))
                application.refresh_from_db()
                self.assertIsNotNone(application.deleted_at)

    def test_non_owner_cannot_delete_application(self):
        application = Application.objects.create(owner=self.other_user, rooms_count=2, location="Buxoro")
        self.assertEqual(self.client.get(reverse("applications:delete", args=[application.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("applications:delete", args=[application.pk])).status_code, 404)
        application.refresh_from_db()
        self.assertIsNone(application.deleted_at)

    def test_deleted_order_leaves_the_architect_market(self):
        arch_user = User.objects.create_user(phone="+998901110000", first_name="A", last_name="R", role=User.Role.ARCHITECT)
        from architects.models import ArchitectProfile
        from wallet.models import Wallet
        architect = ArchitectProfile.objects.create(user=arch_user, bio="x")
        Wallet.objects.create(architect=architect, balance=20)
        application = Application.objects.create(owner=self.user, rooms_count=2, location="Nukus")
        self.client.post(reverse("applications:delete", args=[application.pk]))
        self.client.force_login(arch_user)
        self.assertNotContains(self.client.get("/freelancer/dashboard/?tab=market"), "Nukus")
        self.assertEqual(self.client.get(reverse("offers:architect_apply", args=[application.pk])).status_code, 404)


class DeleteOrderRefundTests(TestCase):
    """Architects who paid to apply get their coins back when the order is deleted."""

    def setUp(self):
        from architects.models import ArchitectProfile
        from offers.models import Offer
        from offers.services import send_offer
        from wallet.models import Wallet
        self.client_user = User.objects.create_user(phone="+998907654321", first_name="M", last_name="R", role=User.Role.USER)
        self.application = Application.objects.create(owner=self.client_user, rooms_count=3, location="Toshkent")
        self.architects = []
        for i in range(2):
            user = User.objects.create_user(phone=f"+99890111111{i}", first_name=f"A{i}", last_name="R", role=User.Role.ARCHITECT)
            profile = ArchitectProfile.objects.create(user=user, bio="x")
            Wallet.objects.create(architect=profile, balance=20)
            send_offer(self.application, profile, source=Offer.Source.ARCHITECT_APPLIED)
            self.architects.append(profile)
        self.client.force_login(self.client_user)

    def balances(self):
        return [p.wallet.__class__.objects.get(pk=p.wallet.pk).balance for p in self.architects]

    def test_confirmation_page_does_not_burden_the_client_with_coin_talk(self):
        response = self.client.get(reverse("applications:delete", args=[self.application.pk]))
        self.assertNotContains(response, "tanga")
        self.assertContains(response, "2 ta ariza rad etiladi")
        self.assertEqual(self.balances(), [10, 10])  # nothing refunded yet

    def test_deleting_refunds_every_architect_and_rejects_their_offers(self):
        from offers.models import Offer
        from wallet.models import CoinTransaction
        self.client.post(reverse("applications:delete", args=[self.application.pk]))
        self.assertEqual(self.balances(), [20, 20])
        self.assertEqual(CoinTransaction.objects.filter(reason=CoinTransaction.Reason.OFFER_REFUND).count(), 2)
        self.assertEqual(set(Offer.objects.values_list("status", flat=True)), {Offer.Status.REJECTED})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.CANCELLED)

    def test_refund_happens_only_once(self):
        from applications.services import delete_application
        delete_application(self.application)
        delete_application(self.application)
        self.assertEqual(self.balances(), [20, 20])

    def test_invited_architects_are_not_refunded_anything(self):
        from architects.models import ArchitectProfile
        from offers.models import Offer
        from offers.services import send_offer
        from wallet.models import Wallet
        user = User.objects.create_user(phone="+998901119999", first_name="I", last_name="N", role=User.Role.ARCHITECT)
        invited = ArchitectProfile.objects.create(user=user, bio="x")
        Wallet.objects.create(architect=invited, balance=5)
        send_offer(self.application, invited, source=Offer.Source.USER_INVITED)
        self.client.post(reverse("applications:delete", args=[self.application.pk]))
        self.assertEqual(Wallet.objects.get(architect=invited).balance, 5)

    def test_deleting_an_in_progress_order_refunds_the_accepted_architect(self):
        from offers.models import Offer
        from offers.services import accept_offer
        offer = Offer.objects.filter(architect=self.architects[0]).get()
        accept_offer(offer)  # also rejects the other architect's offer
        self.client.post(reverse("applications:delete", args=[self.application.pk]))
        self.assertEqual(self.balances()[0], 20)   # the accepted architect got theirs back
        self.assertEqual(self.balances()[1], 10)   # the already-rejected one is not refunded twice
        self.assertFalse(Offer.objects.filter(status=Offer.Status.ACCEPTED).exists())


class ApplicationDescriptionTests(TestCase):
    def test_client_can_describe_what_needs_doing(self):
        user = User.objects.create_user(phone="+998901234567", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(user)
        response = self.client.post(reverse("applications:post"), {
            "size_m2": 120, "rooms_count": 4, "location": "Toshkent",
            "description": "Zamonaviy uy loyihasi kerak.",
        })
        self.assertEqual(response.status_code, 302)
        application = Application.objects.get()
        self.assertEqual(application.description, "Zamonaviy uy loyihasi kerak.")
        detail = self.client.get(reverse("applications:detail", args=[application.pk]))
        self.assertContains(detail, "Zamonaviy uy loyihasi kerak.")


class OrderExpiryTests(TestCase):
    """Open orders with no accepted architect vanish after 31 days unless confirmed."""

    def setUp(self):
        from architects.models import ArchitectProfile
        from offers.models import Offer
        from offers.services import send_offer
        from wallet.models import Wallet
        self.owner = User.objects.create_user(phone="+998907654321", first_name="M", last_name="R", role=User.Role.USER)
        self.application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        user = User.objects.create_user(phone="+998901111110", first_name="A", last_name="R", role=User.Role.ARCHITECT)
        self.architect = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.architect, balance=20)
        send_offer(self.application, self.architect, source=Offer.Source.ARCHITECT_APPLIED)  # 20 -> 10
        self.client.force_login(self.owner)

    def age(self, days, application=None):
        from datetime import timedelta
        from django.utils import timezone
        application = application or self.application
        Application.objects.filter(pk=application.pk).update(last_confirmed_at=timezone.now() - timedelta(days=days))

    def balance(self):
        self.wallet.refresh_from_db()
        return self.wallet.balance

    def test_a_new_order_has_31_days(self):
        self.application.refresh_from_db()
        self.assertEqual(self.application.days_left, 31)
        self.assertFalse(self.application.expiring_soon)

    def test_owner_is_warned_when_posting_and_on_the_order_page(self):
        self.assertContains(self.client.get(reverse("applications:post")), "31 kun ichida")
        page = self.client.get(reverse("applications:detail", args=[self.application.pk]))
        self.assertContains(page, "31 kundan keyin avtomatik")
        self.assertContains(page, "Hali ham izlayapman")

    def test_dashboard_shows_the_countdown_and_turns_red_in_the_last_week(self):
        self.age(20)
        page = self.client.get(reverse("applications:dashboard"))
        self.assertContains(page, "11 kundan keyin avtomatik")
        self.assertNotContains(page, "bg-red-600")            # no urgent button yet
        self.age(26)
        page = self.client.get(reverse("applications:dashboard"))
        self.assertContains(page, "5 kundan keyin avtomatik")
        self.assertContains(page, "Hali ham izlayapman")

    def test_order_is_deleted_after_31_days_and_architect_is_refunded(self):
        from applications.services import expire_stale_applications
        from offers.models import Offer
        from wallet.models import CoinTransaction
        self.age(32)
        self.assertEqual(expire_stale_applications(), 1)
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.deleted_at)
        self.assertTrue(self.application.auto_deleted)
        self.assertEqual(self.application.status, Application.Status.CANCELLED)
        self.assertEqual(self.balance(), 20)   # the 10 coins came back
        self.assertEqual(CoinTransaction.objects.filter(reason=CoinTransaction.Reason.OFFER_REFUND).count(), 1)
        self.assertEqual(Offer.objects.get().status, Offer.Status.REJECTED)
        self.assertEqual(expire_stale_applications(), 0)   # nothing more to do, no double refund
        self.assertEqual(self.balance(), 20)

    def test_confirming_restarts_the_31_days(self):
        from applications.services import expire_stale_applications
        self.age(30)
        response = self.client.post(reverse("applications:renew", args=[self.application.pk]))
        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.days_left, 31)
        self.age(-0)  # untouched
        self.assertEqual(expire_stale_applications(), 0)
        self.assertEqual(self.balance(), 10)   # architect keeps waiting, still paid

    def test_only_the_owner_can_confirm(self):
        other = User.objects.create_user(phone="+998907777770", first_name="O", last_name="T", role=User.Role.USER)
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("applications:renew", args=[self.application.pk])).status_code, 404)

    def test_orders_with_an_accepted_architect_never_expire(self):
        from applications.services import expire_stale_applications
        from offers.models import Offer
        from offers.services import accept_offer
        accept_offer(Offer.objects.get())
        self.age(100)
        self.assertEqual(expire_stale_applications(), 0)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.deleted_at)

    def test_viewing_the_dashboard_cleans_up_and_tells_the_owner(self):
        self.age(40)
        page = self.client.get(reverse("applications:dashboard"))
        self.assertContains(page, "avtomatik o'chirildi")
        self.assertContains(page, "Toshkent")     # named in the notice
        self.assertEqual(self.balance(), 20)      # refunded during that page load

    def test_architect_market_never_shows_or_lets_you_take_an_expired_order(self):
        self.age(40)
        self.client.force_login(self.architect.user)
        market = self.client.get("/freelancer/dashboard/?tab=market")
        self.assertNotIn(self.application.pk, [a.pk for a in market.context["open_applications"]])
        self.assertContains(market, "Rad etildi")   # their own history shows the offer as rejected
        self.assertEqual(self.balance(), 20)
        self.assertEqual(self.client.get(reverse("offers:architect_apply", args=[self.application.pk])).status_code, 404)

    def test_management_command_expires_orders(self):
        from django.core.management import call_command
        self.age(40)
        call_command("expire_applications")
        self.application.refresh_from_db()
        self.assertTrue(self.application.auto_deleted)
        self.assertEqual(self.balance(), 20)


class ExpireOrdersEndpointTests(TestCase):
    def test_disabled_without_a_secret(self):
        from django.test import override_settings
        with override_settings(CRON_SECRET=""):
            self.assertEqual(self.client.get("/internal/expire-orders/").status_code, 403)
            self.assertEqual(self.client.get("/internal/expire-orders/?token=").status_code, 403)

    def test_needs_the_right_secret_and_accepts_bearer_or_token(self):
        from django.test import override_settings
        with override_settings(CRON_SECRET="s3cret"):
            self.assertEqual(self.client.get("/internal/expire-orders/?token=nope").status_code, 403)
            self.assertEqual(self.client.get("/internal/expire-orders/", HTTP_AUTHORIZATION="Bearer wrong").status_code, 403)
            ok = self.client.get("/internal/expire-orders/", HTTP_AUTHORIZATION="Bearer s3cret")
            self.assertContains(ok, "removed: 0")
            self.assertEqual(self.client.get("/internal/expire-orders/?token=s3cret").status_code, 200)


class ConfirmButtonLockTests(TestCase):
    """"Hali ham izlayapman" unlocks 15 days after posting; pressing it restarts the 31 days."""

    def setUp(self):
        self.owner = User.objects.create_user(phone="+998907654321", first_name="M", last_name="R", role=User.Role.USER)
        self.application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        self.client.force_login(self.owner)
        self.detail = reverse("applications:detail", args=[self.application.pk])
        self.renew = reverse("applications:renew", args=[self.application.pk])

    def age(self, days):
        from datetime import timedelta
        from django.utils import timezone
        Application.objects.filter(pk=self.application.pk).update(last_confirmed_at=timezone.now() - timedelta(days=days))
        self.application.refresh_from_db()

    def test_button_is_locked_for_the_first_15_days(self):
        self.age(3)
        page = self.client.get(self.detail)
        self.assertContains(page, "disabled")
        self.assertContains(page, "Tugma 12 kundan keyin bosiladigan bo")
        self.assertFalse(page.context["application"].can_renew)

    def test_pressing_it_too_early_changes_nothing(self):
        self.age(10)
        before = self.application.last_confirmed_at
        response = self.client.post(self.renew, follow=True)
        self.application.refresh_from_db()
        self.assertEqual(self.application.last_confirmed_at, before)      # timer untouched
        self.assertContains(response, "5 kundan keyin ochiladi")

    def test_button_unlocks_after_15_days_and_resets_the_timer(self):
        self.age(15)
        page = self.client.get(self.detail)
        self.assertTrue(page.context["application"].can_renew)
        self.assertNotContains(page, "bosiladigan bo")
        self.client.post(self.renew)
        self.application.refresh_from_db()
        self.assertEqual(self.application.days_left, 31)
        self.assertFalse(self.application.can_renew)                       # locked again for 15 days

    def test_dashboard_shows_the_button_only_once_it_can_be_pressed(self):
        self.age(5)
        self.assertNotContains(self.client.get(reverse("applications:dashboard")), "Hali ham izlayapman")
        self.age(16)
        self.assertContains(self.client.get(reverse("applications:dashboard")), "Hali ham izlayapman")

    def test_the_warning_is_short_and_never_talks_about_coins(self):
        for url in (self.detail, reverse("applications:post")):
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertContains(page, "avtomatik o'chiriladi")
                self.assertContains(page, "Hali ham izlayapman")
                self.assertNotContains(page, "tanga")
                self.assertNotContains(page, "qaytariladi")
        self.age(35)   # the notice after an automatic deletion is just as plain
        page = self.client.get(reverse("applications:dashboard"))
        self.assertContains(page, "avtomatik o'chirildi")
        self.assertNotContains(page, "tanga")


class HouseImageTests(TestCase):
    """The optional "Uy rasmi" upload (a picture of the house, or a PDF)."""

    GIF = (
        b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04"
        b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
    )

    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings
        self._media = tempfile.mkdtemp(prefix="poydevor-test-media-")
        self._override = override_settings(MEDIA_ROOT=self._media)
        self._override.enable()
        self.addCleanup(lambda: (self._override.disable(), shutil.rmtree(self._media, ignore_errors=True)))
        self.user = User.objects.create_user(phone="+998901234567", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(self.user)

    def post(self, upload):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse("applications:post"), {
            "size_m2": 100, "rooms_count": 3, "location": "Toshkent", "plan_pdf": upload,
        })

    def test_label_says_house_picture_not_plan(self):
        page = self.client.get(reverse("applications:post"))
        self.assertContains(page, "Uy rasmi (ixtiyoriy)")
        self.assertNotContains(page, "rejasi")
        self.assertContains(page, 'accept=".pdf,.jpg,.jpeg,application/pdf,image/jpeg"')   # PDF or JPG only

    def test_a_photo_is_accepted_and_shown_as_a_picture(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (6, 6), "blue").save(buffer, "JPEG")
        response = self.post(SimpleUploadedFile("uy.jpg", buffer.getvalue(), content_type="image/jpeg"))
        self.assertEqual(response.status_code, 302)
        application = Application.objects.get()
        self.assertTrue(application.plan_is_image)
        detail = self.client.get(reverse("applications:detail", args=[application.pk]))
        self.assertContains(detail, "Uy rasmi")
        self.assertContains(detail, f'<img src="{application.plan_pdf.url}"')
        self.assertNotContains(detail, "rejasi")

    def test_a_pdf_is_still_accepted_and_shown_as_a_download(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.post(SimpleUploadedFile("uy.pdf", b"%PDF-1.4", content_type="application/pdf"))
        application = Application.objects.get()
        self.assertFalse(application.plan_is_image)
        self.assertContains(self.client.get(reverse("applications:detail", args=[application.pk])), "Yuklab olish")

    def test_dangerous_file_types_are_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.post(SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("plan_pdf"))
        self.assertFalse(Application.objects.exists())

    def test_other_picture_and_document_types_are_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        for name in ["uy.gif", "uy.png", "uy.dwg", "uy.zip"]:
            response = self.post(SimpleUploadedFile(name, self.GIF, content_type="application/octet-stream"))
            self.assertEqual(response.status_code, 200, name)
            self.assertTrue(response.context["form"].errors.get("plan_pdf"), name)
        self.assertFalse(Application.objects.exists())


class OfferCardShowsThePortfolioTests(TestCase):
    def test_each_application_shows_the_architects_profile_and_links_to_their_page(self):
        from architects.models import ArchitectProfile, Skill
        from offers.models import Offer
        owner = User.objects.create_user(phone="+998901010101", first_name="Mijoz", role=User.Role.USER)
        arch_user = User.objects.create_user(phone="+998902020202", first_name="Nodir", last_name="Karimov", role=User.Role.ARCHITECT)
        arch = ArchitectProfile.objects.create(user=arch_user, bio="Ko'p yillik tajriba", rating="4.50")
        arch.skills.add(Skill.objects.create(name="Interyer dizayni"))
        app = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        Offer.objects.create(application=app, architect=arch, source="architect_applied")
        self.client.force_login(owner)
        page = self.client.get(reverse("applications:detail", args=[app.pk]))
        for text in ("Nodir Karimov", "Interyer dizayni", "4,50", "Portfolioni to&#x27;liq ko&#x27;rish".replace("&#x27;", "'")):
            self.assertContains(page, text)
        self.assertContains(page, reverse("architects:detail", args=[arch.pk]))
