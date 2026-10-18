from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style
from offers.models import Offer
from wallet.models import Wallet


MARKET_URL = "/freelancer/dashboard/?tab=market"


class PublicListViewTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.modern = Style.objects.create(name="Zamonaviy")
        self.classic = Style.objects.create(name="Klassik")
        self.profile.styles.add(self.modern)

    def test_list_shows_architect(self):
        response = self.client.get(reverse("architects:list"))
        self.assertContains(response, "Nodir")

    def test_filter_by_style_excludes_non_matching(self):
        other_user = User.objects.create_user(
            phone="+998907654321", password="x",
            first_name="Malika", last_name="Rashidova", role=User.Role.ARCHITECT,
        )
        other_profile = ArchitectProfile.objects.create(user=other_user, bio="y")
        other_profile.styles.add(self.classic)

        response = self.client.get(reverse("architects:list"), {"style": self.modern.id})
        self.assertContains(response, "Nodir")
        self.assertNotContains(response, "Malika")


class ProjectGalleryViewTests(TestCase):
    def _build_profile_with_project(self, phone, first_name, style):
        user = User.objects.create_user(
            phone=phone, password="x", first_name=first_name, last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        profile = ArchitectProfile.objects.create(user=user, bio="x")
        profile.styles.add(style)
        project = PortfolioProject.objects.create(architect=profile, title=f"{first_name} loyihasi", style=style)
        return profile, project

    def setUp(self):
        self.modern = Style.objects.create(name="Zamonaviy")
        self.classic = Style.objects.create(name="Klassik")
        self.profile_a, self.project_a = self._build_profile_with_project(
            "+998901112200", "Nodir", self.modern,
        )
        self.profile_b, self.project_b = self._build_profile_with_project(
            "+998901112201", "Malika", self.classic,
        )

    def test_gallery_lists_projects_from_multiple_architects(self):
        response = self.client.get(reverse("architects:project_gallery"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nodir loyihasi")
        self.assertContains(response, "Malika loyihasi")

    def test_style_filter_excludes_non_matching_projects(self):
        response = self.client.get(reverse("architects:project_gallery"), {"style": self.modern.id})
        self.assertContains(response, "Nodir loyihasi")
        self.assertNotContains(response, "Malika loyihasi")

    def test_gallery_card_links_to_the_project_page(self):
        response = self.client.get(reverse("architects:project_gallery"))
        expected_url = reverse("architects:project_detail", args=[self.project_a.pk])
        self.assertContains(response, f'href="{expected_url}"')


class PublicDetailViewTests(TestCase):
    def _build_profile_with_projects(self, project_count):
        user = User.objects.create_user(
            phone=f"+9989{project_count:07d}", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        profile = ArchitectProfile.objects.create(user=user, bio="x")
        style = Style.objects.create(name=f"Style-{project_count}")
        profile.styles.add(style)
        for i in range(project_count):
            project = PortfolioProject.objects.create(
                architect=profile, title=f"Loyiha {i}", style=style,
            )
            PortfolioImage.objects.create(project=project, image=f"portfolio/{i}-a.jpg", order=0)
            PortfolioImage.objects.create(project=project, image=f"portfolio/{i}-b.jpg", order=1)
        return profile, style

    def test_filtered_detail_prefetches_project_images(self):
        # Query count for a style-filtered detail page must not scale with
        # the number of projects — that would indicate the filter dropped
        # the images prefetch and the template is issuing a query per
        # project (the N+1 regression the review flagged).
        small_profile, small_style = self._build_profile_with_projects(2)
        large_profile, large_style = self._build_profile_with_projects(6)

        with CaptureQueriesContext(connection) as small_ctx:
            small_response = self.client.get(
                reverse("architects:detail", args=[small_profile.id]),
                {"style": small_style.id},
            )
        with CaptureQueriesContext(connection) as large_ctx:
            large_response = self.client.get(
                reverse("architects:detail", args=[large_profile.id]),
                {"style": large_style.id},
            )

        self.assertEqual(small_response.status_code, 200)
        self.assertEqual(large_response.status_code, 200)
        self.assertEqual(len(small_ctx.captured_queries), len(large_ctx.captured_queries))


class ArchitectRoleGateTests(TestCase):
    def setUp(self):
        self.regular_user = User.objects.create_user(
            phone="+998909998877", password="x",
            first_name="Oddiy", last_name="Foydalanuvchi", role=User.Role.USER,
        )
        self.client.force_login(self.regular_user)

    def test_regular_user_cannot_register_as_architect(self):
        response = self.client.get(reverse("architects:register_freelancer"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.assertFalse(ArchitectProfile.objects.filter(user=self.regular_user).exists())

    def test_regular_user_cannot_access_dashboard(self):
        response = self.client.get(reverse("architects:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))


class ProjectCreateViewTests(TestCase):
    """A whole portfolio project is created in one step."""

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
        self.user = User.objects.create_user(
            phone="+998901112233", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        self.style = Style.objects.create(name="Zamonaviy")
        self.client.force_login(self.user)
        self.url = reverse("architects:project_create")

    def gif(self, name):
        return SimpleUploadedFile(name, self.GIF, content_type="image/gif")

    def post(self, title="Birinchi loyiha", **extra):
        data = {
            "title": title, "style": self.style.id, "images": [self.gif("a.gif"), self.gif("b.gif")],
            "attachment": SimpleUploadedFile("taqdimot.pdf", b"%PDF-1.4", content_type="application/pdf"),
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_one_form_creates_the_project_with_its_photos_in_order(self):
        response = self.post(description="Tavsif", attachment=SimpleUploadedFile("taqdimot.pdf", b"%PDF-1.4", content_type="application/pdf"))
        self.assertEqual(response.status_code, 302)
        project = PortfolioProject.objects.get(title="Birinchi loyiha")
        self.assertEqual((project.style, project.description, project.order), (self.style, "Tavsif", 1))
        self.assertEqual([i.order for i in project.images.all()], [0, 1])
        self.assertEqual(project.cover, project.images.first())          # the first photo is the cover
        self.assertTrue(project.attachment.name.endswith(".pdf"))

    def test_description_is_optional_but_a_photo_and_a_file_are_not(self):
        self.assertEqual(self.post().status_code, 302)                     # no description
        no_file = self.client.post(self.url, {"title": "Fayzsiz", "style": self.style.id, "images": [self.gif("a.gif")]})
        self.assertTrue(no_file.context["form"].errors.get("attachment"))
        self.assertFalse(PortfolioProject.objects.filter(title="Fayzsiz").exists())
        no_photo = self.client.post(self.url, {"title": "Rasmsiz", "style": self.style.id})
        self.assertEqual(no_photo.status_code, 200)
        self.assertTrue(no_photo.context["form"].errors.get("images"))
        self.assertFalse(PortfolioProject.objects.filter(title="Rasmsiz").exists())   # nothing half-created

    def test_title_and_type_are_required(self):
        response = self.client.post(self.url, {"images": [self.gif("a.gif")]})
        self.assertEqual(set(response.context["form"].errors), {"title", "style", "attachment"})

    def test_orders_are_assigned_automatically(self):
        self.post("Birinchi loyiha")
        self.post("Ikkinchi loyiha")
        first, second = PortfolioProject.objects.order_by("id")
        self.assertGreater(second.order, first.order)

    def test_wrong_file_types_are_refused(self):
        bad_photo = self.post("A", images=[SimpleUploadedFile("plan.pdf", b"%PDF", content_type="application/pdf")])
        self.assertTrue(bad_photo.context["form"].errors.get("images"))
        bad_file = self.post("B", attachment=SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"))
        self.assertTrue(bad_file.context["form"].errors.get("attachment"))
        self.assertFalse(PortfolioProject.objects.exists())

    def test_the_form_is_compact_with_no_second_step_and_no_favourite_photo_marking(self):
        html = self.client.get(self.url).content.decode()
        for field in ('name="title"', 'name="style"', 'name="description"', 'name="images"', 'name="attachment"'):
            self.assertIn(field, html)
        self.assertNotIn("asosiy", html.lower())
        self.assertNotIn("yulduzcha", html.lower())
        self.assertIn("birinchi rasm kartochkada ko", html)


class ProjectImageAddViewTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings
        media = tempfile.mkdtemp(prefix="poydevor-test-media-")
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(lambda: (override.disable(), shutil.rmtree(media, ignore_errors=True)))
        self.user = User.objects.create_user(
            phone="+998901112244", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        self.style = Style.objects.create(name="Zamonaviy")
        self.project = PortfolioProject.objects.create(
            architect=self.profile, title="Loyiha", description="desc", style=self.style, order=1,
        )
        self.client.force_login(self.user)

    def _image_file(self, name="test.gif"):
        gif = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04"
            b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        )
        return SimpleUploadedFile(name, gif, content_type="image/gif")

    def test_add_image_without_order_field_succeeds_and_auto_assigns_order(self):
        url = reverse("architects:project_image_add", args=[self.project.id])
        response = self.client.post(url, {"images": [self._image_file("a.gif")]})
        self.assertEqual(response.status_code, 302)
        first_image = self.project.images.get()
        self.assertEqual(first_image.order, 1)

        response = self.client.post(url, {"images": [self._image_file("b.gif")]})
        self.assertEqual(response.status_code, 302)
        second_image = self.project.images.exclude(id=first_image.id).get()
        self.assertGreater(second_image.order, first_image.order)


class DashboardOpenApplicationsSlotIndicatorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998904445566", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.user = User.objects.create_user(
            phone="+998901112255", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        Wallet.objects.create(architect=self.profile, balance=100)
        self.client.force_login(self.user)

    def _make_application(self):
        return Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")

    def _other_architect(self, phone):
        other_user = User.objects.create_user(
            phone=phone, password="x", first_name="Boshqa", last_name="Arxitektor", role=User.Role.ARCHITECT,
        )
        other_profile = ArchitectProfile.objects.create(user=other_user, bio="y")
        Wallet.objects.create(architect=other_profile, balance=100)
        return other_profile

    def test_zero_pending_offers_shows_0_of_3(self):
        application = self._make_application()
        response = self.client.get(MARKET_URL)
        self.assertEqual(response.status_code, 200)
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 0)
        self.assertContains(response, "0/3")

    def test_one_pending_offer_shows_1_of_3(self):
        application = self._make_application()
        architect_2 = self._other_architect("+998902223311")
        Offer.objects.create(application=application, architect=architect_2, source=Offer.Source.USER_INVITED)
        response = self.client.get(MARKET_URL)
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 1)
        self.assertContains(response, "1/3")

    def test_two_pending_offers_shows_2_of_3(self):
        application = self._make_application()
        architect_2 = self._other_architect("+998902223312")
        architect_3 = self._other_architect("+998902223313")
        Offer.objects.create(application=application, architect=architect_2, source=Offer.Source.USER_INVITED)
        Offer.objects.create(application=application, architect=architect_3, source=Offer.Source.USER_INVITED)
        response = self.client.get(MARKET_URL)
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 2)
        self.assertContains(response, "2/3")

    def test_three_pending_offers_shows_3_of_3_and_disables_cta(self):
        application = self._make_application()
        architect_2 = self._other_architect("+998902223314")
        architect_3 = self._other_architect("+998902223315")
        architect_4 = self._other_architect("+998902223316")
        Offer.objects.create(application=application, architect=architect_2, source=Offer.Source.USER_INVITED)
        Offer.objects.create(application=application, architect=architect_3, source=Offer.Source.USER_INVITED)
        Offer.objects.create(application=application, architect=architect_4, source=Offer.Source.USER_INVITED)
        response = self.client.get(MARKET_URL)
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 3)
        self.assertContains(response, "3/3")
        self.assertContains(response, "Joylar band")  # badge on the card

    def test_architect_with_existing_pending_offer_sees_already_applied_state(self):
        application = self._make_application()
        Offer.objects.create(
            application=application, architect=self.profile, source=Offer.Source.ARCHITECT_APPLIED,
        )
        response = self.client.get(MARKET_URL)
        self.assertContains(response, "Ariza yuborilgan")  # badge on the card


class CoverPhotoTests(TestCase):
    """A project's first photo is its cover, shown first on every card."""

    def setUp(self):
        user = User.objects.create_user(phone="+998901234000", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.style = Style.objects.create(name="Zamonaviy")
        self.project_a = PortfolioProject.objects.create(architect=self.profile, title="Birinchi uy", style=self.style, order=1)
        self.project_b = PortfolioProject.objects.create(architect=self.profile, title="Ikkinchi uy", style=self.style, order=2)
        for project, tag in ((self.project_a, "a"), (self.project_b, "b")):
            for i in range(3):
                PortfolioImage.objects.create(project=project, image=f"portfolio/{tag}-{i}.jpg", order=i)

    def test_the_cover_is_the_first_photo(self):
        self.assertEqual(self.project_a.cover.image.name, "portfolio/a-0.jpg")

    def test_architect_card_shows_one_cover_per_project(self):
        html = self.client.get(reverse("architects:list")).content.decode()
        self.assertEqual(html.count('<img src="/media/portfolio/'), 2)
        self.assertIn('<img src="/media/portfolio/a-0.jpg"', html)
        self.assertIn('<img src="/media/portfolio/b-0.jpg"', html)
        self.assertNotIn('<img src="/media/portfolio/a-1.jpg"', html)
        self.assertEqual([i.image.name for i in self.profile.carousel_images], ["portfolio/a-0.jpg", "portfolio/b-0.jpg"])

    def test_project_card_shows_all_of_that_projects_photos_first_one_first(self):
        html = self.client.get(reverse("architects:project_gallery")).content.decode()
        card = html.split("Birinchi uy</h3>")[0].rsplit("<article", 1)[1]
        self.assertLess(card.index("a-0.jpg"), card.index("a-1.jpg"))
        self.assertLess(card.index("a-1.jpg"), card.index("a-2.jpg"))
        self.assertNotIn("b-0.jpg", card)                               # never mixed with another project

    def test_a_card_without_photos_shows_a_placeholder_not_a_slider(self):
        PortfolioImage.objects.all().delete()
        response = self.client.get(reverse("architects:list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'x-data="carousel()"')

    def test_adding_photos_later_keeps_the_first_one_as_cover(self):
        import shutil, tempfile
        from django.test import override_settings
        media = tempfile.mkdtemp(prefix="poydevor-test-media-")
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        gif = (b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04"
               b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b")
        self.client.force_login(self.profile.user)
        with override_settings(MEDIA_ROOT=media):
            self.client.post(reverse("architects:project_image_add", args=[self.project_a.pk]),
                             {"images": [SimpleUploadedFile("new.gif", gif, content_type="image/gif")]})
        images = list(self.project_a.images.all())
        self.assertEqual(len(images), 4)
        self.assertEqual(images[0].image.name, "portfolio/a-0.jpg")     # still the cover
        self.assertTrue(images[-1].image.name.endswith("new.gif") or "new" in images[-1].image.name)

    def test_there_is_no_favourite_photo_marking_any_more(self):
        self.assertFalse(hasattr(PortfolioImage, "is_main"))
        with self.assertRaises(Exception):
            reverse("architects:image_toggle_main", args=[1])
        self.client.force_login(self.profile.user)
        page = self.client.get(reverse("architects:project_image_add", args=[self.project_a.pk]))
        self.assertNotContains(page, "asosiy rasm")
        self.assertNotContains(page, "yulduzcha")


class ArchitectAndProjectCardContentTests(TestCase):
    """Cards show only: image, title, type, architect name and rating."""

    def setUp(self):
        user = User.objects.create_user(phone="+998901235555", first_name="Nodir", last_name="Karimov", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=user, bio="x", rating="4.50")
        style = Style.objects.create(name="Zamonaviy")
        self.project = PortfolioProject.objects.create(
            architect=self.profile, title="Panorama uyi", style=style, description="JUDA UZUN TAVSIF", order=1,
        )
        PortfolioImage.objects.create(project=self.project, image="portfolio/p.jpg", order=0)

    def test_project_card(self):
        page = self.client.get(reverse("architects:project_gallery"))
        for expected in ("Panorama uyi", "Zamonaviy", "Nodir Karimov", "4,50"):
            self.assertContains(page, expected)
        self.assertNotContains(page, "JUDA UZUN TAVSIF")                 # no description on the card
        self.assertContains(page, reverse("architects:project_detail", args=[self.project.pk]))

    def test_architect_card(self):
        page = self.client.get(reverse("architects:list"))
        for expected in ("Nodir Karimov", "Zamonaviy", "4,50"):
            self.assertContains(page, expected)
        self.assertNotContains(page, "JUDA UZUN TAVSIF")
        self.assertNotContains(page, "loyiha yakunlangan")               # nothing beyond the basics
        self.assertContains(page, reverse("architects:detail", args=[self.profile.pk]))

    def test_a_studio_card_carries_the_studios_name(self):
        from architects.models import Studio
        self.profile.kind = ArchitectProfile.Kind.STUDIO_OWNER
        self.profile.save()
        Studio.objects.create(
            owner=self.profile, name="ArcDes Studio", founded_on="2020-05-15", founders="A", responsible_person="A",
            responsible_birth_date="1992-08-12", email="a@a.uz", phone="+998901235555", staff_count=3, projects_count=4,
        )
        for url in (reverse("architects:list"), reverse("architects:project_gallery")):
            self.assertContains(self.client.get(url), "ArcDes Studio")

    def test_typography_title_then_type(self):
        html = self.client.get(reverse("architects:project_gallery")).content.decode()
        self.assertIn("text-lg font-semibold", html.split("Panorama uyi</h3>")[0].rsplit("<h3", 1)[1])
        style_tag = html.split("Zamonaviy</p>")[0].rsplit("<p", 1)[1]
        self.assertIn("text-[15px]", style_tag)
        self.assertIn("font-medium", style_tag)

    def test_every_page_has_the_full_size_viewer_available(self):
        for url in (reverse("architects:list"), reverse("architects:project_gallery"),
                    reverse("architects:detail", args=[self.profile.pk]),
                    reverse("architects:project_detail", args=[self.project.pk])):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'x-data="lightbox()"')


class ProjectDetailPageTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(phone="+998901236666", first_name="Nodir", last_name="Karimov", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=user, bio="x", rating="4.00")
        self.profile.skills.add(Skill.objects.create(name="3D vizualizatsiya"))
        style = Style.objects.create(name="Zamonaviy")
        self.project = PortfolioProject.objects.create(
            architect=self.profile, title="Panorama uyi", style=style, description="Batafsil tavsif shu yerda.",
            attachment="portfolio_files/taqdimot.pdf", order=1,
        )
        for i in range(3):
            PortfolioImage.objects.create(project=self.project, image=f"portfolio/d{i}.jpg", order=i)
        self.other = PortfolioProject.objects.create(architect=self.profile, title="Boshqa uy", style=style, order=2)
        PortfolioImage.objects.create(project=self.other, image="portfolio/o.jpg", order=0)
        self.url = reverse("architects:project_detail", args=[self.project.pk])

    def test_shows_everything_about_the_project(self):
        page = self.client.get(self.url)
        for expected in ("Panorama uyi", "Zamonaviy", "Batafsil tavsif shu yerda.", "taqdimot.pdf", "Faylni ochish"):
            self.assertContains(page, expected)
        for i in range(3):
            self.assertContains(page, f"portfolio/d{i}.jpg")

    def test_shows_the_architect_with_rating_skills_and_other_projects(self):
        page = self.client.get(self.url)
        for expected in ("Nodir Karimov", "4,00", "3D vizualizatsiya", "Ariza yuborish", "Boshqa uy"):
            self.assertContains(page, expected)
        self.assertContains(page, reverse("architects:project_detail", args=[self.other.pk]))   # other projects, at the bottom
        client = User.objects.create_user(phone="+998901239999", first_name="Mijoz", role=User.Role.USER)
        self.client.force_login(client)
        self.assertContains(self.client.get(self.url), reverse("offers:send", args=[self.profile.pk]))   # apply straight from here
        self.assertLess(page.content.decode().index("3D vizualizatsiya"), page.content.decode().index("<h1"))
        self.assertNotContains(page, "Rasm qo&#x27;shish")                 # no owner tools for visitors
        self.assertNotContains(page, "Rasm qo'shish")

    def test_a_hidden_projects_page_does_not_exist(self):
        self.profile.portfolio_exempt = False
        self.profile.save()                                              # incomplete portfolio -> hidden
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_architect_page_lists_project_cards_that_open_the_details(self):
        page = self.client.get(reverse("architects:detail", args=[self.profile.pk]))
        self.assertContains(page, reverse("architects:project_detail", args=[self.project.pk]))
        self.assertNotContains(page, "Batafsil tavsif shu yerda.")        # descriptions live only on the detail page

    def test_owner_sees_their_own_project_with_tools(self):
        self.client.force_login(self.profile.user)
        page = self.client.get(reverse("architects:my_project", args=[self.project.pk]))
        self.assertContains(page, "Batafsil tavsif shu yerda.")
        self.assertContains(page, "Rasm qo'shish")
        self.assertContains(page, "taqdimot.pdf")
        self.assertNotContains(page, "Arxitektor</p>")                    # no "the architect" box on your own page

    def test_nobody_else_can_open_someone_elses_owner_page(self):
        other_user = User.objects.create_user(phone="+998901237777", first_name="O", last_name="T", role=User.Role.ARCHITECT)
        ArchitectProfile.objects.create(user=other_user, bio="x")
        self.client.force_login(other_user)
        self.assertEqual(self.client.get(reverse("architects:my_project", args=[self.project.pk])).status_code, 404)


class ProjectEditDeleteTests(TestCase):
    GIF = (b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04"
           b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b")

    def setUp(self):
        self.user = User.objects.create_user(phone="+998901117777", first_name="Nodir", last_name="Karimov", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=self.user)
        self.style = Style.objects.create(name="Zamonaviy")
        self.project = PortfolioProject.objects.create(architect=self.profile, title="Eski nom", style=self.style, order=1)
        self.img1 = PortfolioImage.objects.create(project=self.project, image="portfolio/a.jpg", order=0)
        self.img2 = PortfolioImage.objects.create(project=self.project, image="portfolio/b.jpg", order=1)
        self.client.force_login(self.user)
        other = User.objects.create_user(phone="+998901118888", first_name="Boshqa", last_name="Odam", role=User.Role.ARCHITECT)
        self.other_profile = ArchitectProfile.objects.create(user=other)

    def test_owner_page_has_edit_and_delete(self):
        page = self.client.get(reverse("architects:my_project", args=[self.project.pk]))
        self.assertContains(page, reverse("architects:project_edit", args=[self.project.pk]))
        self.assertContains(page, reverse("architects:project_delete", args=[self.project.pk]))

    def test_a_project_can_be_edited_and_a_file_is_needed_when_it_has_none(self):
        url = reverse("architects:project_edit", args=[self.project.pk])
        data = {"title": "Yangi nom", "style": self.style.pk, "description": "Yangi tavsif"}
        self.assertTrue(self.client.post(url, data).context["form"].errors.get("attachment"))
        import shutil, tempfile
        from django.test import override_settings
        media = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with override_settings(MEDIA_ROOT=media):
            data["attachment"] = SimpleUploadedFile("reja.pdf", b"%PDF-1.4", content_type="application/pdf")
            response = self.client.post(url, data)
        self.assertRedirects(response, reverse("architects:my_project", args=[self.project.pk]), fetch_redirect_response=False)
        self.project.refresh_from_db()
        self.assertEqual((self.project.title, self.project.description), ("Yangi nom", "Yangi tavsif"))
        # Later edits keep the file unless a new one is chosen.
        self.client.post(url, {"title": "Yana nom", "style": self.style.pk})
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, "Yana nom")
        self.assertTrue(self.project.attachment.name.endswith(".pdf"))

    def test_a_photo_can_be_removed_but_never_the_last_one(self):
        first = reverse("architects:project_photo_delete", args=[self.project.pk, self.img1.pk])
        self.client.post(first)
        self.assertEqual(self.project.images.count(), 1)
        self.client.post(reverse("architects:project_photo_delete", args=[self.project.pk, self.img2.pk]))
        self.assertEqual(self.project.images.count(), 1)

    def test_a_project_is_deleted_only_after_confirming(self):
        url = reverse("architects:project_delete", args=[self.project.pk])
        self.assertContains(self.client.get(url), "Loyiha o'chirilsinmi?")
        self.assertTrue(PortfolioProject.objects.filter(pk=self.project.pk).exists())
        self.assertRedirects(self.client.post(url), "/freelancer/dashboard/?tab=room", fetch_redirect_response=False)
        self.assertFalse(PortfolioProject.objects.filter(pk=self.project.pk).exists())

    def test_nobody_else_can_touch_the_project(self):
        self.client.force_login(self.other_profile.user)
        for name in ("project_edit", "project_delete"):
            self.assertEqual(self.client.post(reverse(f"architects:{name}", args=[self.project.pk]), {}).status_code, 404)
        self.assertTrue(PortfolioProject.objects.filter(pk=self.project.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(reverse("architects:project_edit", args=[self.project.pk])).status_code, 302)

    def test_profile_page_offers_a_photo_upload(self):
        html = self.client.get(reverse("architects:portfolio_edit")).content.decode()
        self.assertIn('name="avatar"', html)
        self.assertIn("Profil rasmi", html)
