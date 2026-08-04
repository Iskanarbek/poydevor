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


class OnboardingViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.client.force_login(self.user)
        self.skill = Skill.objects.create(name="3D vizualizatsiya")

    def test_onboarding_creates_profile(self):
        response = self.client.post(reverse("architects:onboarding"), {
            "bio": "10 yillik tajriba", "skills": [self.skill.id],
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ArchitectProfile.objects.filter(user=self.user).exists())

    def test_onboarding_without_skills_shows_form_error(self):
        response = self.client.post(reverse("architects:onboarding"), {
            "bio": "10 yillik tajriba", "skills": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("skills"))
        self.assertFalse(ArchitectProfile.objects.filter(user=self.user).exists())


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

    def test_regular_user_cannot_access_onboarding(self):
        response = self.client.post(reverse("architects:onboarding"), {"bio": "test"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.assertFalse(ArchitectProfile.objects.filter(user=self.regular_user).exists())

    def test_regular_user_cannot_access_dashboard(self):
        response = self.client.get(reverse("architects:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))


class ProjectCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901112233", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        self.style = Style.objects.create(name="Zamonaviy")
        self.client.force_login(self.user)

    def test_create_without_order_field_succeeds_and_auto_assigns_order(self):
        response = self.client.post(reverse("architects:project_create"), {
            "title": "Birinchi loyiha", "description": "desc", "style": self.style.id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PortfolioProject.objects.filter(title="Birinchi loyiha").exists())
        first_project = PortfolioProject.objects.get(title="Birinchi loyiha")
        self.assertEqual(first_project.order, 1)

        response = self.client.post(reverse("architects:project_create"), {
            "title": "Ikkinchi loyiha", "description": "desc", "style": self.style.id,
        })
        self.assertEqual(response.status_code, 302)
        second_project = PortfolioProject.objects.get(title="Ikkinchi loyiha")
        self.assertGreater(second_project.order, first_project.order)


class ProjectImageAddViewTests(TestCase):
    def setUp(self):
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
        response = self.client.post(url, {"image": self._image_file("a.gif")})
        self.assertEqual(response.status_code, 302)
        first_image = self.project.images.get()
        self.assertEqual(first_image.order, 1)

        response = self.client.post(url, {"image": self._image_file("b.gif")})
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
        response = self.client.get(reverse("architects:dashboard"))
        self.assertEqual(response.status_code, 200)
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 0)
        self.assertContains(response, "0/3")

    def test_one_pending_offer_shows_1_of_3(self):
        application = self._make_application()
        architect_2 = self._other_architect("+998902223311")
        Offer.objects.create(application=application, architect=architect_2, source=Offer.Source.USER_INVITED)
        response = self.client.get(reverse("architects:dashboard"))
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 1)
        self.assertContains(response, "1/3")

    def test_two_pending_offers_shows_2_of_3(self):
        application = self._make_application()
        architect_2 = self._other_architect("+998902223312")
        architect_3 = self._other_architect("+998902223313")
        Offer.objects.create(application=application, architect=architect_2, source=Offer.Source.USER_INVITED)
        Offer.objects.create(application=application, architect=architect_3, source=Offer.Source.USER_INVITED)
        response = self.client.get(reverse("architects:dashboard"))
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
        response = self.client.get(reverse("architects:dashboard"))
        ctx_app = response.context["open_applications"].get(pk=application.pk)
        self.assertEqual(ctx_app.pending_offers_count, 3)
        self.assertContains(response, "3/3")
        apply_url = reverse("offers:architect_apply", args=[application.pk])
        self.assertNotContains(response, f'href="{apply_url}"')
        self.assertContains(response, "Barcha joylar band")

    def test_architect_with_existing_pending_offer_sees_already_applied_state(self):
        application = self._make_application()
        Offer.objects.create(
            application=application, architect=self.profile, source=Offer.Source.ARCHITECT_APPLIED,
        )
        response = self.client.get(reverse("architects:dashboard"))
        apply_url = reverse("offers:architect_apply", args=[application.pk])
        self.assertNotContains(response, f'href="{apply_url}"')
        self.assertContains(response, "Siz allaqachon ariza yubordingiz")
