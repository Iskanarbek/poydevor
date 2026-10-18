from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile, Skill, Style


class SeedLookupsCommandTests(TestCase):
    def test_creates_styles_and_skills_but_no_accounts(self):
        call_command("seed_lookups")
        self.assertTrue(Style.objects.exists())
        self.assertTrue(Skill.objects.exists())
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(ArchitectProfile.objects.count(), 0)

    def test_is_idempotent(self):
        call_command("seed_lookups")
        styles, skills = Style.objects.count(), Skill.objects.count()
        call_command("seed_lookups")
        self.assertEqual((Style.objects.count(), Skill.objects.count()), (styles, skills))
