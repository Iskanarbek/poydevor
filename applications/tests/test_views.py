from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application


def jpeg_upload(name="uy.jpg"):
    import io
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (6, 6), "blue").save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def order_data(**overrides):
    """A complete, valid "post an order" form (every question answered, estimate agreed to)."""
    data = {
        "size_m2": 120, "object_type": "yard", "service_type": "interior", "rooms_count": 4,
        "location": "Toshkent", "files": [jpeg_upload()], "price_confirmed": "on",
    }
    data.update(overrides)
    return data


class PostApplicationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_post_application_known_size(self):
        response = self.client.post(reverse("applications:post"), order_data())
        self.assertEqual(response.status_code, 302)
        app = Application.objects.get()
        self.assertRedirects(response, reverse("applications:choose", args=[app.pk]), fetch_redirect_response=False)   # next: who gets it?
        app = Application.objects.get()
        self.assertEqual((app.size_m2, app.object_type, app.service_type), (120, "yard", "interior"))
        self.assertEqual((app.estimate_min, app.estimate_max), (1500, 2750))      # the estimate is stored

    def test_every_question_is_required(self):
        for missing in ("size_m2", "object_type", "service_type", "rooms_count", "location", "price_confirmed"):
            with self.subTest(missing=missing):
                data = order_data()
                del data[missing]
                response = self.client.post(reverse("applications:post"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors.get(missing))
        self.assertFalse(Application.objects.exists())

    def test_the_estimate_is_computed_by_the_server_not_taken_from_the_browser(self):
        self.client.post(reverse("applications:post"), order_data(estimate_min=1, estimate_max=2))
        self.assertEqual(Application.objects.get().estimate_min, 1500)

    def test_own_style_is_saved_when_other_is_chosen(self):
        self.client.post(reverse("applications:post"), order_data(interior_style="other", custom_style="Skandinav"))
        app = Application.objects.get()
        self.assertEqual((app.interior_style, app.style_label), (None, "Skandinav"))

    def test_choosing_other_without_writing_a_style_is_refused(self):
        response = self.client.post(reverse("applications:post"), order_data(interior_style="other"))
        self.assertTrue(response.context["form"].errors.get("custom_style"))

    def test_a_listed_style_drops_any_typed_text(self):
        from architects.models import Style
        style = Style.objects.create(name="Loft")
        self.client.post(reverse("applications:post"), order_data(interior_style=style.pk, custom_style="x"))
        app = Application.objects.get()
        self.assertEqual((app.interior_style, app.custom_style), (style, ""))

    def test_the_live_estimate_endpoint(self):
        url = reverse("applications:price_estimate")
        ok = self.client.get(url, {"size": 120, "object_type": "yard", "service_type": "interior", "rooms": 4, "location": "Toshkent"})
        self.assertEqual(ok.json(), {"ok": True, "min": 1500, "max": 2750})
        self.assertEqual(self.client.get(url, {"size": 120}).json(), {"ok": False})

    def test_posting_page_has_no_auto_delete_warning(self):
        page = self.client.get(reverse("applications:post"))
        self.assertNotContains(page, "avtomatik o'chiriladi")
        self.assertNotContains(page, "Hali ham izlayapman")


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_home_page_has_create_button_the_gallery_and_no_expiry_warnings(self):
        response = self.client.get(reverse("applications:dashboard"))
        self.assertContains(response, "Buyurtma yaratish")
        self.assertContains(response, "buyurtmangizni shu arxitektorga yuboring")
        self.assertNotContains(response, "avtomatik")
        self.assertNotContains(response, "Hali ham izlayapman")
        self.assertIn("projects", response.context)

    def test_clients_menu_says_bosh_sahifa_and_has_no_separate_gallery_link(self):
        response = self.client.get(reverse("applications:dashboard"))
        self.assertContains(response, "Bosh sahifa")
        self.assertNotContains(response, ">Barcha loyihalar<")

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
        self.assertEqual(self.balances(), [19, 19])  # nothing refunded yet

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
        self.assertEqual(self.balances()[1], 19)   # the already-rejected one is not refunded twice
        self.assertFalse(Offer.objects.filter(status=Offer.Status.ACCEPTED).exists())


class ApplicationDescriptionTests(TestCase):
    def test_client_can_describe_what_needs_doing(self):
        user = User.objects.create_user(phone="+998901234567", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(user)
        response = self.client.post(reverse("applications:post"), order_data(description="Zamonaviy uy loyihasi kerak."))
        self.assertEqual(response.status_code, 302)
        application = Application.objects.get()
        self.assertEqual(application.description, "Zamonaviy uy loyihasi kerak.")
        Application.objects.filter(pk=application.pk).update(publication="public")
        detail = self.client.get(reverse("applications:detail", args=[application.pk]))
        self.assertContains(detail, "Zamonaviy uy loyihasi kerak.")


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

    def post(self, *uploads):
        return self.client.post(reverse("applications:post"), order_data(files=list(uploads)))

    def open_to_all(self, application):
        Application.objects.filter(pk=application.pk).update(publication="public")

    def test_label_says_house_picture_not_plan(self):
        page = self.client.get(reverse("applications:post"))
        self.assertContains(page, "Uy rasmi yoki kadastr")
        self.assertNotContains(page, "rejasi")
        self.assertContains(page, 'accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/*"')   # PDF or a photo
        self.assertContains(page, "multiple")                                                       # several at once

    def test_several_photos_and_files_can_be_attached_and_are_all_shown(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.post(jpeg_upload("a.jpg"), jpeg_upload("b.jpg"), SimpleUploadedFile("kadastr.pdf", b"%PDF-1.4", content_type="application/pdf"))
        self.assertEqual(response.status_code, 302)
        application = Application.objects.get()
        self.assertEqual(application.files.count(), 3)
        self.open_to_all(application)
        detail = self.client.get(reverse("applications:detail", args=[application.pk]))
        for f in application.files.all():
            self.assertContains(detail, f.file.url)
        self.assertContains(detail, "kadastr")

    def test_architects_see_all_of_them_before_applying(self):
        from architects.models import ArchitectProfile
        self.post(jpeg_upload("a.jpg"), jpeg_upload("b.jpg"))
        application = Application.objects.get()
        self.open_to_all(application)
        arch_user = User.objects.create_user(phone="+998909990001", first_name="N", last_name="K", role=User.Role.ARCHITECT)
        ArchitectProfile.objects.create(user=arch_user, portfolio_exempt=True)
        self.client.force_login(arch_user)
        page = self.client.get(reverse("offers:architect_apply", args=[application.pk]))
        for f in application.files.all():
            self.assertContains(page, f.file.url)

    def test_too_many_files_are_refused(self):
        response = self.post(*[jpeg_upload(f"{i}.jpg") for i in range(11)])
        self.assertTrue(response.context["form"].errors.get("files"))
        self.assertFalse(Application.objects.exists())

    def test_a_pdf_is_accepted_and_shown_as_a_download(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.post(SimpleUploadedFile("uy.pdf", b"%PDF-1.4", content_type="application/pdf"))
        application = Application.objects.get()
        self.assertFalse(application.files.get().is_image)
        self.open_to_all(application)
        self.assertContains(self.client.get(reverse("applications:detail", args=[application.pk])), "uy.pdf")

    def test_dangerous_file_types_are_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.post(SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("files"))
        self.assertFalse(Application.objects.exists())

    def test_other_picture_and_document_types_are_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        for name in ["uy.gif", "uy.dwg", "uy.zip"]:
            response = self.post(SimpleUploadedFile(name, self.GIF, content_type="application/octet-stream"))
            self.assertEqual(response.status_code, 200, name)
            self.assertTrue(response.context["form"].errors.get("files"), name)
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


class BothServicesFileAndBudgetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="+998901234567", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(self.user)

    def test_both_services_can_be_ticked_and_are_priced_together(self):
        data = order_data(service_type=["architecture", "interior"])
        self.client.post(reverse("applications:post"), data)
        app = Application.objects.get()
        self.assertEqual(app.service_type, "both")
        self.assertEqual(app.get_service_type_display(), "Arxitektura loyihasi + Interyer dizayni")
        self.assertEqual((app.estimate_min, app.estimate_max), (2350, 4250))     # house: architecture + interior

    def test_one_service_still_works_and_none_is_refused(self):
        self.client.post(reverse("applications:post"), order_data(service_type="architecture"))
        self.assertEqual(Application.objects.get().service_type, "architecture")
        response = self.client.post(reverse("applications:post"), order_data(service_type=[]))
        self.assertTrue(response.context["form"].errors.get("service_type"))

    def test_the_house_file_is_optional_and_a_phone_photo_is_fine(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        from PIL import Image
        data = order_data()
        del data["files"]
        self.assertEqual(self.client.post(reverse("applications:post"), data).status_code, 302)
        buffer = io.BytesIO()
        Image.new("RGB", (6, 6), "green").save(buffer, "PNG")
        response = self.client.post(reverse("applications:post"), order_data(files=[SimpleUploadedFile("surat.png", buffer.getvalue(), content_type="image/png")]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Application.objects.order_by("-pk").first().files.get().is_image)
        fake = self.client.post(reverse("applications:post"), order_data(files=[SimpleUploadedFile("x.png", b"not a picture", content_type="image/png")]))
        self.assertEqual(fake.status_code, 200)

    def test_there_is_no_budget_question_anywhere(self):
        page = self.client.get(reverse("applications:post"))
        self.assertNotContains(page, "Byudjet")
        self.assertNotIn("budget", page.context["form"].fields)


class TwoStepPublishingTests(TestCase):
    """A new order is saved but invisible; its owner then either opens it to everyone or sends it to
    ONE architect, never both."""

    def setUp(self):
        from architects.models import ArchitectProfile
        self.owner = User.objects.create_user(phone="+998901000001", first_name="Aziz", last_name="K", role=User.Role.USER)
        a1 = User.objects.create_user(phone="+998902000001", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT)
        a2 = User.objects.create_user(phone="+998902000002", first_name="Malika", last_name="R", role=User.Role.ARCHITECT)
        self.arch1 = ArchitectProfile.objects.create(user=a1, portfolio_exempt=True)
        self.arch2 = ArchitectProfile.objects.create(user=a2, portfolio_exempt=True)
        from wallet.models import Wallet
        Wallet.objects.create(architect=self.arch1, balance=5)
        Wallet.objects.create(architect=self.arch2, balance=5)
        self.client.force_login(self.owner)
        self.client.post(reverse("applications:post"), order_data())
        self.order = Application.objects.get()

    def market_places(self, user):
        self.client.force_login(user)
        page = self.client.get("/freelancer/dashboard/?tab=market")
        return {a.pk for a in page.context["open_applications"]}

    def test_a_new_order_is_saved_but_invisible_to_architects(self):
        self.assertEqual(self.order.publication, "draft")
        self.assertNotIn(self.order.pk, self.market_places(self.arch1.user))
        self.client.force_login(self.arch1.user)
        self.assertEqual(self.client.get(reverse("offers:architect_apply", args=[self.order.pk])).status_code, 404)

    def test_opening_a_draft_again_always_shows_the_two_options(self):
        page = self.client.get(reverse("applications:detail", args=[self.order.pk]))
        self.assertRedirects(page, reverse("applications:choose", args=[self.order.pk]), fetch_redirect_response=False)
        choose = self.client.get(reverse("applications:choose", args=[self.order.pk]))
        self.assertContains(choose, "Hammaga ochiq qilish")
        self.assertContains(choose, "Arxitektorlarni ko")
        home = self.client.get(reverse("applications:dashboard"))
        self.assertContains(home, "Yuborilmagan")

    def test_choosing_everyone_makes_it_public_and_tells_architects(self):
        response = self.client.post(reverse("applications:choose", args=[self.order.pk]), {"audience": "public"})
        self.assertRedirects(response, reverse("applications:dashboard"), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertEqual(self.order.publication, "public")
        self.assertIn(self.order.pk, self.market_places(self.arch1.user))
        from notifications.models import Notification
        self.assertTrue(Notification.objects.filter(user=self.arch1.user, text__contains="Yangi e'lon").exists())
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("applications:detail", args=[self.order.pk])), "Hammaga ochiq")

    def test_sending_to_one_architect_keeps_it_out_of_the_market_and_shows_who_got_it(self):
        self.client.get(reverse("applications:pick_architect", args=[self.order.pk]))
        banner = self.client.get(reverse("architects:list"))
        self.assertContains(banner, "e'loni yuborish uchun")
        send_url = reverse("offers:send", args=[self.arch1.pk])
        form = self.client.get(send_url)
        self.assertEqual(form.context["preselected"], self.order.pk)
        response = self.client.post(send_url, {"application": self.order.pk})
        self.assertRedirects(response, reverse("applications:dashboard"), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertEqual((self.order.publication, self.order.sent_to), ("direct", self.arch1))
        self.assertNotIn(self.order.pk, self.market_places(self.arch2.user))     # nobody else sees it
        self.client.force_login(self.owner)
        detail = self.client.get(reverse("applications:detail", args=[self.order.pk]))
        self.assertContains(detail, "E'lon yuborilgan")
        self.assertContains(detail, self.arch1.display_name)

    def test_it_cannot_be_both_public_and_direct(self):
        self.client.post(reverse("applications:choose", args=[self.order.pk]), {"audience": "public"})
        send = self.client.post(reverse("offers:send", args=[self.arch1.pk]), {"application": self.order.pk})
        self.assertEqual(send.status_code, 404)                                    # only unsent drafts can be sent
        self.assertEqual(self.client.get(reverse("applications:choose", args=[self.order.pk])).status_code, 302)
        other = Application.objects.create(owner=self.owner, rooms_count=1, location="Buxoro", publication="draft")
        self.client.post(reverse("offers:send", args=[self.arch1.pk]), {"application": other.pk})
        self.client.post(reverse("applications:choose", args=[other.pk]), {"audience": "public"})
        other.refresh_from_db()
        self.assertEqual(other.publication, "direct")                              # stays direct

    def test_declining_returns_it_to_the_unsent_state_so_it_can_be_sent_again(self):
        self.client.post(reverse("offers:send", args=[self.arch1.pk]), {"application": self.order.pk})
        from offers.models import Offer
        offer = Offer.objects.get()
        self.client.force_login(self.arch1.user)
        self.client.post(reverse("offers:respond", args=[offer.pk]), {"decision": "reject"})
        self.order.refresh_from_db()
        self.assertEqual((self.order.publication, self.order.sent_to), ("draft", None))
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.get(reverse("applications:detail", args=[self.order.pk])), reverse("applications:choose", args=[self.order.pk]), fetch_redirect_response=False)

    def test_cancelling_a_delete_goes_to_the_home_page_not_the_order(self):
        page = self.client.get(reverse("applications:delete", args=[self.order.pk]))
        self.assertContains(page, f'href="{reverse("applications:dashboard")}"')
        self.assertNotContains(page, f'href="{reverse("applications:detail", args=[self.order.pk])}"')

    def test_password_fields_get_an_eye_button(self):
        self.client.logout()
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, "data-eye")


class LiveEstimateWithBothServicesTests(TestCase):
    def test_the_estimate_endpoint_prices_both_and_the_page_sends_both(self):
        user = User.objects.create_user(phone="+998901234500", first_name="A", last_name="B", role=User.Role.USER)
        self.client.force_login(user)
        url = reverse("applications:price_estimate")
        both = self.client.get(url, {"size": 100, "object_type": "apartment", "service_type": "both", "rooms": 3, "location": "Toshkent"}).json()
        one = self.client.get(url, {"size": 100, "object_type": "apartment", "service_type": "interior", "rooms": 3, "location": "Toshkent"}).json()
        self.assertGreater(both["min"], one["min"])
        self.assertContains(self.client.get(reverse("applications:post")), "getAll('service_type')")


class ChangeAudienceTests(TwoStepPublishingTests):
    """The owner may change "public / one architect" until someone applies or accepts; the detail page
    ends with an orange "Bosh sahifaga qaytish" button."""

    def setUp(self):
        super().setUp()
        self.change_url = reverse("applications:change_audience", args=[self.order.pk])

    def make_public(self):
        self.client.post(reverse("applications:choose", args=[self.order.pk]), {"audience": "public"})
        self.order.refresh_from_db()

    def test_the_detail_page_ends_with_the_back_button(self):
        self.make_public()
        page = self.client.get(reverse("applications:detail", args=[self.order.pk]))
        self.assertContains(page, "Bosh sahifaga qaytish")
        self.assertContains(page, "Yuborish usulini o")

    def test_a_public_order_nobody_applied_to_can_be_taken_back_and_resent(self):
        self.make_public()
        self.assertTrue(self.order.can_change_audience)
        response = self.client.post(self.change_url)
        self.assertRedirects(response, reverse("applications:choose", args=[self.order.pk]), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertEqual(self.order.publication, "draft")
        self.assertNotIn(self.order.pk, self.market_places(self.arch1.user))          # gone from the market again

    def test_once_someone_applied_it_is_too_late(self):
        from offers.services import send_offer
        self.make_public()
        send_offer(self.order, self.arch1, source="architect_applied")
        self.client.force_login(self.owner)
        self.assertFalse(Application.objects.get(pk=self.order.pk).can_change_audience)
        response = self.client.post(self.change_url)
        self.assertRedirects(response, reverse("applications:detail", args=[self.order.pk]), fetch_redirect_response=False)
        self.assertEqual(Application.objects.get(pk=self.order.pk).publication, "public")
        self.assertContains(self.client.get(reverse("applications:detail", args=[self.order.pk])), "o'zgartirib bo")

    def test_a_direct_order_can_be_taken_back_until_the_architect_accepts(self):
        from notifications.models import Notification
        from offers.models import Offer
        self.client.post(reverse("offers:send", args=[self.arch1.pk]), {"application": self.order.pk})
        self.order.refresh_from_db()
        self.assertEqual(self.order.publication, "direct")
        self.client.post(self.change_url)
        self.order.refresh_from_db()
        self.assertEqual((self.order.publication, self.order.sent_to), ("draft", None))
        self.assertFalse(Offer.objects.exists())                                     # the invitation was withdrawn
        self.assertTrue(Notification.objects.filter(user=self.arch1.user, text__contains="qaytarib oldi").exists())
        # send to the other architect instead, who accepts: now it is final
        self.client.post(reverse("offers:send", args=[self.arch2.pk]), {"application": self.order.pk})
        offer = Offer.objects.get()
        self.client.force_login(self.arch2.user)
        self.client.post(reverse("offers:respond", args=[offer.pk]), {"decision": "accept"})
        self.client.force_login(self.owner)
        self.client.post(self.change_url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.publication, "direct")

    def test_only_the_owner_and_only_by_post(self):
        self.make_public()
        self.assertEqual(self.client.get(self.change_url).status_code, 405)
        self.client.force_login(self.arch1.user)
        self.assertEqual(self.client.post(self.change_url).status_code, 404)
