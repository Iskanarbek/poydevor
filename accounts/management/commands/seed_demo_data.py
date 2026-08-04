import random
import urllib.request

from django.core.files.base import ContentFile
from django.db import models as django_models
from django.core.management.base import BaseCommand

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style
from wallet.models import Wallet
from wallet.services import topup_coins

HOUSE_PHOTO_URLS = [
    "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200&q=80",
    "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=1200&q=80",
    "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=1200&q=80",
    "https://images.unsplash.com/photo-1613977257363-707ba9348227?w=1200&q=80",
    "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1200&q=80",
    "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=1200&q=80",
    "https://images.unsplash.com/photo-1582268611958-ebfd161ef9cf?w=1200&q=80",
    "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=1200&q=80",
    "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?w=1200&q=80",
    "https://images.unsplash.com/photo-1600585152220-90363fe7e115?w=1200&q=80",
    "https://images.unsplash.com/photo-1600566752355-35792bedcfea?w=1200&q=80",
    "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?w=1200&q=80",
    "https://images.unsplash.com/photo-1523217582562-09d0def993a6?w=1200&q=80",
    "https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=1200&q=80",
    "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=1200&q=80",
    "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?w=1200&q=80",
    "https://images.unsplash.com/photo-1600047509358-9dc75507daeb?w=1200&q=80",
    "https://images.unsplash.com/photo-1616137466211-f939a420be84?w=1200&q=80",
    "https://images.unsplash.com/photo-1502005229762-cf1b2da7c5d6?w=1200&q=80",
    "https://images.unsplash.com/photo-1600573472550-8090b5e0745e?w=1200&q=80",
    "https://images.unsplash.com/photo-1600585152915-d208bec867a1?w=1200&q=80",
    "https://images.unsplash.com/photo-1613977257592-4871e5fcd7c4?w=1200&q=80",
    "https://images.unsplash.com/photo-1615529182904-14819c35db37?w=1200&q=80",
    "https://images.unsplash.com/photo-1600566753151-384129cf4e3e?w=1200&q=80",
    "https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?w=1200&q=80",
    "https://images.unsplash.com/photo-1494526585095-c41746248156?w=1200&q=80",
    "https://images.unsplash.com/photo-1600585154526-990dced4db0d?w=1200&q=80",
    "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=1200&q=80",
    "https://images.unsplash.com/photo-1592595896616-c37162298647?w=1200&q=80",
    "https://images.unsplash.com/photo-1600210492493-0946911123ea?w=1200&q=80",
    "https://images.unsplash.com/photo-1618221469555-7f3ad97540d6?w=1200&q=80",
    "https://images.unsplash.com/photo-1524230659092-07f99a75c013?w=1200&q=80",
]

PORTRAIT_URLS = [
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&q=80",
    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&q=80",
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&q=80",
    "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?w=400&q=80",
    "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&q=80",
]

RICH_ARCHITECT_PASSWORD = "arxitektor123"

RICH_ARCHITECTS = [
    {
        "phone": "+998901111111",
        "first_name": "Alisher",
        "last_name": "Karimov",
        "bio": (
            "10 yildan ortiq tajribaga ega me'mor, zamonaviy va minimalistik "
            "uy loyihalari bo'yicha ixtisoslashgan. Har bir loyihada funksionallik "
            "va estetikani muvozanatda saqlashga harakat qilaman."
        ),
        "avatar_url": PORTRAIT_URLS[0],
        "styles": ["Zamonaviy", "Minimalizm"],
        "skills": ["3D vizualizatsiya", "Interyer dizayni"],
        "coins": 250,
        "telegram_username": "alisher_arch",
        "projects": [
            ("Zamonaviy ikki qavatli uy", "Zamonaviy"),
            ("Minimalistik shahar uyi", "Minimalizm"),
            ("Panorama oynali kottedj", "Zamonaviy"),
        ],
    },
    {
        "phone": "+998902222222",
        "first_name": "Dilnoza",
        "last_name": "Yusupova",
        "bio": (
            "Klassik va neoklassik uslubdagi villalar bo'yicha 8 yillik tajribaga ega "
            "me'mor. Mijozlarning didiga mos, hashamatli va bezakli loyihalar yarataman."
        ),
        "avatar_url": PORTRAIT_URLS[1],
        "styles": ["Klassik", "Neoklassik"],
        "skills": ["Interyer dizayni", "Landshaft dizayni"],
        "coins": 180,
        "telegram_username": "dilnoza_design",
        "projects": [
            ("Klassik villa loyihasi", "Klassik"),
            ("Neoklassik ikki qavatli uy", "Neoklassik"),
        ],
    },
    {
        "phone": "+998903333333",
        "first_name": "Jasur",
        "last_name": "Toshmatov",
        "bio": (
            "Loft va hay-tek uslubidagi noyob loyihalar bilan mashhur me'mor. "
            "12 yillik tajriba davomida ko'plab tijorat va turar-joy binolarini loyihalashtirganman."
        ),
        "avatar_url": PORTRAIT_URLS[2],
        "styles": ["Loft", "Xay-tek"],
        "skills": ["3D vizualizatsiya", "Qurilish nazorati"],
        "coins": 300,
        "telegram_username": "jasur_loft",
        "projects": [
            ("Sanoat uslubidagi loft uy", "Loft"),
            ("Xay-tek uslubidagi villa", "Xay-tek"),
            ("Ochiq rejali loft kvartira", "Loft"),
            ("Aqlli uy tizimli kottedj", "Xay-tek"),
        ],
    },
    {
        "phone": "+998904444444",
        "first_name": "Madina",
        "last_name": "Nurullayeva",
        "bio": (
            "Hovlili kottedjlar va oilaviy uylar bo'yicha ixtisoslashgan me'mor. "
            "6 yillik tajribam davomida qulay va ekologik toza yashash makonlarini yarataman."
        ),
        "avatar_url": PORTRAIT_URLS[3],
        "styles": ["Minimalizm", "Zamonaviy"],
        "skills": ["Landshaft dizayni"],
        "coins": 120,
        "telegram_username": "madina_uy",
        "projects": [
            ("Hovlili kottedj", "Minimalizm"),
            ("Bog' uyli zamonaviy villa", "Zamonaviy"),
        ],
    },
    {
        "phone": "+998905555555",
        "first_name": "Sardor",
        "last_name": "Rashidov",
        "bio": (
            "Klassik, neoklassik va zamonaviy uslublarni birlashtirgan aralash loyihalar "
            "ustasi. 15 yillik tajriba bilan yirik villalar va ko'p qavatli uylarni loyihalashtiraman."
        ),
        "avatar_url": PORTRAIT_URLS[4],
        "styles": ["Klassik", "Neoklassik", "Zamonaviy"],
        "skills": ["3D vizualizatsiya", "Interyer dizayni"],
        "coins": 220,
        "telegram_username": "sardor_projects",
        "projects": [
            ("Hashamatli klassik villa", "Klassik"),
            ("Neoklassik oilaviy uy", "Neoklassik"),
            ("Zamonaviy ko'p qavatli uy", "Zamonaviy"),
        ],
    },
]

PROJECT_DESCRIPTIONS = [
    "Ushbu loyihada zamonaviy arxitektura yechimlari va sifatli materiallar qo'llanildi. "
    "Uy egalarining barcha talablari inobatga olingan holda ishlab chiqildi.",
    "Loyiha qulay va funksional makonni yaratishga qaratilgan. "
    "Har bir xona tabiiy yorug'lik va shamollatishni hisobga olgan holda joylashtirilgan.",
    "Bu loyiha mijozning individual ehtiyojlariga moslashtirilgan noyob dizayn yechimi. "
    "Tashqi va ichki bezaklar uyg'un uslubda ishlab chiqilgan.",
    "Zamonaviy texnologiyalar va an'anaviy me'morchilik uslubini uyg'unlashtirgan loyiha. "
    "Energiya samaradorligiga alohida e'tibor qaratilgan.",
]


def download_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


class Command(BaseCommand):
    help = (
        "Creates demo data: styles/skills, a demo architect with 1000 coins, "
        "and several rich architect accounts with portfolios."
    )

    def handle(self, *args, **options):
        for name in ["Zamonaviy", "Klassik", "Minimalizm", "Loft", "Neoklassik", "Xay-tek"]:
            Style.objects.get_or_create(name=name)
        for name in ["3D vizualizatsiya", "Landshaft dizayni", "Interyer dizayni", "Qurilish nazorati"]:
            Skill.objects.get_or_create(name=name)

        self._seed_original_demo_architect()
        self._seed_rich_architects()

    def _seed_original_demo_architect(self):
        demo_phone = "+998900000000"
        if not User.objects.filter(phone=demo_phone).exists():
            user = User.objects.create_user(
                phone=demo_phone, password="demo12345",
                first_name="Demo", last_name="Arxitektor", role=User.Role.ARCHITECT,
            )
            profile = ArchitectProfile.objects.create(user=user, bio="Demo hisob, sinov uchun.")
            wallet = Wallet.objects.create(architect=profile)
            topup_coins(wallet, 1000)
            self.stdout.write(self.style.SUCCESS(f"Demo arxitektor yaratildi: {demo_phone} / demo12345 (1000 tanga)"))
        else:
            self.stdout.write("Demo hisob allaqachon mavjud.")

    def _seed_rich_architects(self):
        photo_pool = list(HOUSE_PHOTO_URLS)

        for data in RICH_ARCHITECTS:
            user, user_created = User.objects.get_or_create(
                phone=data["phone"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "role": User.Role.ARCHITECT,
                },
            )
            if user_created:
                user.set_password(RICH_ARCHITECT_PASSWORD)
                user.save()

            profile, profile_created = ArchitectProfile.objects.get_or_create(
                user=user,
                defaults={
                    "bio": data["bio"],
                    "telegram_username": data["telegram_username"],
                },
            )

            if profile_created:
                self._download_avatar(profile, data)

                styles = list(Style.objects.filter(name__in=data["styles"]))
                skills = list(Skill.objects.filter(name__in=data["skills"]))
                profile.styles.set(styles)
                profile.skills.set(skills)

                wallet, _ = Wallet.objects.get_or_create(architect=profile)
                if wallet.balance == 0:
                    topup_coins(wallet, data["coins"])

                self.stdout.write(
                    self.style.SUCCESS(f"Arxitektor yaratildi: {data['phone']} / {RICH_ARCHITECT_PASSWORD}")
                )
            else:
                Wallet.objects.get_or_create(architect=profile)
                self.stdout.write(f"Arxitektor allaqachon mavjud: {data['phone']}")

            self._seed_projects(profile, data["projects"], photo_pool)

    def _download_avatar(self, profile: ArchitectProfile, data: dict):
        if profile.avatar:
            return
        try:
            avatar_bytes = download_bytes(data["avatar_url"])
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Avatar yuklab olinmadi ({data['phone']}): {exc}"))
            return
        filename = data["avatar_url"].split("/")[-1].split("?")[0] + ".jpg"
        profile.avatar.save(f"{data['phone']}-{filename}", ContentFile(avatar_bytes), save=True)

    def _seed_projects(self, profile: ArchitectProfile, project_specs, photo_pool):
        existing_max_order = (
            PortfolioProject.objects.filter(architect=profile).aggregate(django_models.Max("order"))["order__max"]
            or 0
        )
        next_order = existing_max_order + 1

        for title, style_name in project_specs:
            project, created = PortfolioProject.objects.get_or_create(
                architect=profile,
                title=title,
                defaults={
                    "description": random.choice(PROJECT_DESCRIPTIONS),
                    "style": Style.objects.filter(name=style_name).first(),
                    "order": next_order,
                },
            )
            if created:
                next_order += 1
            self._seed_project_images(project, photo_pool)

    def _seed_project_images(self, project: PortfolioProject, photo_pool):
        if project.images.exists():
            return

        image_count = random.randint(1, 3)
        chosen_urls = random.sample(photo_pool, k=min(image_count, len(photo_pool)))

        for order, url in enumerate(chosen_urls, start=1):
            try:
                image_bytes = download_bytes(url)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"Rasm yuklab olinmadi ({url}): {exc}"))
                continue

            filename = url.split("/")[-1].split("?")[0] + ".jpg"
            portfolio_image = PortfolioImage(project=project, order=order)
            portfolio_image.image.save(f"{project.id}-{order}-{filename}", ContentFile(image_bytes), save=True)
