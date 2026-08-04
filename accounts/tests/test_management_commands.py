import shutil
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import User
from architects.models import PortfolioImage, PortfolioProject

# A tiny valid 1x1 PNG, used as a stand-in for downloaded images/avatars so the
# test doesn't hit the network.
FAKE_IMAGE_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class SeedDemoDataCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="poydevor-test-media-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def _run_seed(self):
        with override_settings(MEDIA_ROOT=self._media_root):
            with patch(
                "accounts.management.commands.seed_demo_data.download_bytes",
                return_value=FAKE_IMAGE_BYTES,
            ):
                call_command("seed_demo_data")

    def test_seed_creates_multiple_architects_with_portfolios(self):
        self._run_seed()

        architect_count = User.objects.filter(role=User.Role.ARCHITECT).count()
        self.assertGreater(architect_count, 1)

        projects_qs = PortfolioProject.objects.all()
        self.assertTrue(projects_qs.exists())

        architects_with_projects = User.objects.filter(
            role=User.Role.ARCHITECT, architect_profile__projects__isnull=False
        ).distinct()
        self.assertTrue(architects_with_projects.exists())

        self.assertTrue(PortfolioImage.objects.exists())

    def test_seed_is_idempotent_on_second_run(self):
        self._run_seed()
        first_architect_count = User.objects.filter(role=User.Role.ARCHITECT).count()
        first_project_count = PortfolioProject.objects.count()
        first_image_count = PortfolioImage.objects.count()

        # Second run should not raise, and should not duplicate data.
        self._run_seed()

        second_architect_count = User.objects.filter(role=User.Role.ARCHITECT).count()
        second_project_count = PortfolioProject.objects.count()
        second_image_count = PortfolioImage.objects.count()

        self.assertEqual(first_architect_count, second_architect_count)
        self.assertEqual(first_project_count, second_project_count)
        self.assertEqual(first_image_count, second_image_count)
