from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioProject, Skill, Style


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
