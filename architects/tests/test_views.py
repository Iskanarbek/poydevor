from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style


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
