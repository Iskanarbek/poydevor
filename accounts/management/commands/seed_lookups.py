from django.core.management.base import BaseCommand

from architects.models import Skill, Style

STYLES = ["Zamonaviy", "Klassik", "Minimalizm", "Loft", "Neoklassik", "Xay-tek"]
SKILLS = ["3D vizualizatsiya", "Landshaft dizayni", "Interyer dizayni", "Qurilish nazorati"]


class Command(BaseCommand):
    help = (
        "Creates the style and skill options used in the dropdowns and filters. "
        "Safe to run repeatedly; it never creates accounts or any other data."
    )

    def handle(self, *args, **options):
        for name in STYLES:
            Style.objects.get_or_create(name=name)
        for name in SKILLS:
            Skill.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f"Uslublar ({len(STYLES)}) va ko'nikmalar ({len(SKILLS)}) tayyor."))
