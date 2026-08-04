from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style


class ArchitectModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )

    def test_create_architect_profile_with_wallet(self):
        profile = ArchitectProfile.objects.create(user=self.user, bio="10 yillik tajriba")
        self.assertEqual(profile.rating, 0)
        self.assertEqual(profile.completed_projects_count, 0)
        self.assertEqual(str(profile), "Nodir Yusupov")

    def test_portfolio_project_with_images_ordering(self):
        profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        style = Style.objects.create(name="Zamonaviy")
        project = PortfolioProject.objects.create(
            architect=profile, title="Villa loyihasi", description="...", style=style,
        )
        img2 = PortfolioImage.objects.create(project=project, image="portfolio/2.jpg", order=2)
        img1 = PortfolioImage.objects.create(project=project, image="portfolio/1.jpg", order=1)
        ordered = list(project.images.all())
        self.assertEqual(ordered, [img1, img2])

    def test_skill_and_style_m2m(self):
        profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        skill = Skill.objects.create(name="3D vizualizatsiya")
        style = Style.objects.create(name="Minimalizm")
        profile.skills.add(skill)
        profile.styles.add(style)
        self.assertIn(skill, profile.skills.all())
        self.assertIn(style, profile.styles.all())
