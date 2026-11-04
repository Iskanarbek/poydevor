"""Fill a LOCAL database with believable demo data so the whole site can be tried by hand:
studios (with logos, workers and portfolios), freelancers, clients, orders, applications and
invitations in every state, assignments with deadlines, and the notifications they cause.

    python manage.py seed_demo          # add the demo people
    python manage.py seed_demo --reset  # remove them first, then add them again

Everything goes through the same services the site itself uses, so what you see (coins,
notifications, assignments) is exactly what real use would produce. Never run it on production.
"""
import random
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw, ImageFont

from accounts.models import User
from applications.models import Application
from applications.pricing import estimate_price
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Studio, Style
from architects.services import decide_verification, set_approval
from offers.models import Offer, StudioAssignment
from offers.services import (
    accept_invitation, accept_offer, assign_worker, claim_assignment, complete_offer, mark_assignment_done, send_offer,
)
from wallet.models import Wallet
from wallet.services import topup_coins

PASSWORD = "123"
Kind = ArchitectProfile.Kind

STUDIOS = [
    ("+998911000001", "ArcDes Studio", "Alisher Qodirov", 2016, (181, 86, 42), "arcdes_studio"),
    ("+998911000002", "Nur Architects", "Nodira Yusupova", 2019, (31, 27, 24), "nur_architects"),
    ("+998911000003", "Modern Group", "Rustam Aliyev", 2012, (60, 90, 120), "modern_group_uz"),
]
EMPLOYEES = {  # studio index -> two workers
    0: [("+998911100001", "Sardor Murodov", "sardor_m"), ("+998911100002", "Kamola Ismoilova", "kamola_i")],
    1: [("+998911100003", "Bekzod Tursunov", "bekzod_t"), ("+998911100004", "Malika Saidova", "malika_s")],
    2: [("+998911100005", "Javohir Karimov", "javohir_k"), ("+998911100006", "Zilola Rahmonova", "zilola_r")],
}
FREELANCERS = [
    ("+998912000001", "Jasur Axmedov", 1994, "jasur_arch"),
    ("+998912000002", "Dilfuza Normatova", 1990, "dilfuza_design"),
    ("+998912000003", "Otabek Sobirov", 1988, ""),
    ("+998912000004", "Shahlo Mirzaeva", 1996, "shahlo_interior"),
    ("+998912000005", "Timur Hasanov", 1992, "timur_h"),
]
CLIENTS = [
    ("+998913000001", "Aziz", "Karimov"),
    ("+998913000002", "Malika", "Rahimova"),
    ("+998913000003", "Bobur", "Tursunov"),
    ("+998913000004", "Dilnoza", "Yusupova"),
]

# title, object type, service, style (name or "own:<text>" or None), price in $ (None = not shown), description
PROJECTS = [
    ("Ikki qavatli zamonaviy uy", "yard", "architecture", "Zamonaviy", 3200, "Planirovka, ustalar uchun chizmalar va fasad ishlab chiqildi."),
    ("Yorug' kvartira interyeri", "apartment", "interior", "Minimalizm", 900, "Uch xonali kvartira uchun to'liq interyer: mebel, yoritish, ranglar."),
    ("Biznes markaz ofisi", "office", "interior", "Xay-tek", 2400, "Ochiq ofis va uchrashuv xonalari, akustik yechimlar."),
    ("Italyan restorani", "restaurant", "interior", "Klassik", 6500, "Zal, bar va oshxona zonasi. Issiq yog'och va yumshoq yoritish."),
    ("To'yxona fasadi", "wedding_hall", "architecture", "Neoklassik", 12000, "500 kishilik to'yxona: bino, kirish guruhi va fasad."),
    ("Loft uslubidagi studiya", "apartment", "interior", "Loft", 450, "Kichik studiya kvartira: g'isht devor, qora metall detallar."),
    ("Hovli va bog' rejasi", "yard", "architecture", None, None, "Uchastka rejalashtiruvi, yo'laklar va yashil zonalar."),
    ("Kafe interyeri", "restaurant", "interior", "own:Skandinav", 1800, "Ochiq ranglar va tabiiy yog'och. Ish kuni davomida yorug' joy."),
    ("Zamonaviy ofis", "office", "architecture", "Zamonaviy", 4100, "Ofis binosi rejasi va fasadi."),
    ("Klassik mehmonxona", "apartment", "interior", "Klassik", 1300, "Katta mehmonxona va oshxona, oltin detallar."),
    ("Villa loyihasi", "yard", "architecture", "Xay-tek", 8800, "Hovlisi bilan villa: 3 qavat, basseyn va garaj."),
    ("Qahvaxona", "restaurant", "architecture", "Loft", 2100, "Kichik qahvaxona binosi va kirish qismi."),
    ("Yosh oila kvartirasi", "apartment", "interior", "own:Art-deko", 700, "Ikki xonali kvartira, bolalar xonasi bilan."),
    ("Tantanalar saroyi interyeri", "wedding_hall", "interior", "Neoklassik", 15500, "Katta zal, sahna va mehmonlar uchun zonalar."),
    ("Shahar uyi", "yard", "architecture", "Minimalizm", 2900, "Tor uchastkada ikki qavatli uy."),
]

ORDER_TEXTS = {
    "yard": "Hovli uy kerak, oilam uchun qulay bo'lsin.",
    "apartment": "Kvartira ta'mirdan keyin chiroyli ko'rinishi kerak.",
    "office": "Kichik jamoa uchun zamonaviy ofis.",
    "restaurant": "Mehmonlar yoqtiradigan issiq muhit.",
    "wedding_hall": "Katta to'yxona, mehmonlar ko'p keladi.",
}


class Command(BaseCommand):
    help = "Fill the local database with demo studios, architects, clients, orders and offers."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove the demo people first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options.get("reset"):
            self.stderr.write("Refusing to seed outside DEBUG (this is for local demos only).")
            return
        rng = random.Random(7)
        demo_phones = (
            [s[0] for s in STUDIOS] + [e[0] for ws in EMPLOYEES.values() for e in ws]
            + [f[0] for f in FREELANCERS] + [c[0] for c in CLIENTS]
        )
        if options["reset"]:
            User.objects.filter(phone__in=demo_phones).delete()
        elif User.objects.filter(phone=STUDIOS[0][0]).exists():
            self.stdout.write("Demo data is already there (use --reset to rebuild it).")
            return

        media = Path(settings.MEDIA_ROOT)
        photos = sorted(f"portfolio/{p.name}" for p in (media / "portfolio").glob("*.jpg"))
        avatars = sorted(f"avatars/{p.name}" for p in (media / "avatars").glob("99890*.jpg"))
        styles = {s.name: s for s in Style.objects.all()}

        def add_projects(profile, count, offset):
            for n in range(count):
                title, obj, service, style, price, text = PROJECTS[(offset + n) % len(PROJECTS)]
                project = PortfolioProject.objects.create(
                    architect=profile, title=title, object_type=obj, service_type=service,
                    style=styles.get(style) if style and not style.startswith("own:") else None,
                    custom_style=style[4:] if style and style.startswith("own:") else "",
                    price_usd=price, description=text, order=n + 1,
                )
                for k in range(rng.choice([1, 2, 3])):
                    PortfolioImage.objects.create(project=project, image=photos[(offset * 3 + n * 2 + k) % len(photos)], order=k)

        def finish(profile):
            set_approval(profile, ArchitectProfile.ApprovalStatus.APPROVED)
            decide_verification(profile, ArchitectProfile.VerificationStatus.VERIFIED)
            wallet, _ = Wallet.objects.get_or_create(architect=profile)
            topup_coins(wallet, 8)

        def logo(name, colour, slug):
            image = Image.new("RGB", (400, 400), colour)
            draw = ImageDraw.Draw(image)
            initials = "".join(w[0] for w in name.split()[:2]).upper()
            try:
                font = ImageFont.load_default(size=170)
            except TypeError:
                font = ImageFont.load_default()
            draw.text((200, 200), initials, fill=(255, 255, 255), anchor="mm", font=font)
            relative = f"avatars/demo-logo-{slug}.jpg"
            image.save(media / relative, "JPEG", quality=90)
            return relative

        studios, workers, freelancers, clients = [], {}, [], []
        for index, (phone, name, person, year, colour, telegram) in enumerate(STUDIOS):
            first, _, last = person.partition(" ")
            user = User.objects.create_user(phone=phone, password=PASSWORD, first_name=first, last_name=last, role=User.Role.ARCHITECT)
            owner = ArchitectProfile.objects.create(
                user=user, kind=Kind.STUDIO_OWNER, approval_status=ArchitectProfile.ApprovalStatus.PENDING,
                telegram_username=telegram, avatar=logo(name, colour, telegram), claimed_projects_count=40,
                bio=f"{name} — {year}-yildan beri uy, ofis va restoran loyihalari.",
            )
            Studio.objects.create(
                owner=owner, name=name, founded_on=date(year, 1, 1), responsible_person=person,
                responsible_birth_date=date(1985 + index, 5, 17), phone=phone, projects_count=40,
            )
            add_projects(owner, 10, index * 4)
            finish(owner)
            studios.append(owner)
            workers[index] = []
            for w_phone, w_name, w_tg in EMPLOYEES[index]:
                wf, _, wl = w_name.partition(" ")
                w_user = User.objects.create_user(phone=w_phone, password=PASSWORD, first_name=wf, last_name=wl, role=User.Role.ARCHITECT)
                employee = ArchitectProfile.objects.create(
                    user=w_user, kind=Kind.STUDIO_EMPLOYEE, studio=owner.studio_owned, telegram_username=w_tg,
                    birth_year=1995, approval_status=ArchitectProfile.ApprovalStatus.PENDING,
                )
                set_approval(employee, ArchitectProfile.ApprovalStatus.APPROVED)
                workers[index].append(employee)

        for index, (phone, name, year, telegram) in enumerate(FREELANCERS):
            first, _, last = name.partition(" ")
            user = User.objects.create_user(phone=phone, password=PASSWORD, first_name=first, last_name=last, role=User.Role.ARCHITECT)
            profile = ArchitectProfile.objects.create(
                user=user, kind=Kind.FREELANCER, approval_status=ArchitectProfile.ApprovalStatus.PENDING,
                telegram_username=telegram, birth_year=year, claimed_projects_count=15,
                avatar=avatars[index % len(avatars)] if avatars else "",
                bio=f"{name}: {2026 - year - 20} yillik tajriba. Interyer va arxitektura loyihalari.",
            )
            add_projects(profile, 5 + index % 2, index * 3 + 1)
            finish(profile)
            freelancers.append(profile)

        for phone, first, last in CLIENTS:
            clients.append(User.objects.create_user(phone=phone, first_name=first, last_name=last, role=User.Role.USER))

        # ---- orders -----------------------------------------------------------------------------
        spec = [  # client, place, rooms, size, object, service, style (name / "own:" / None)
            (0, "Toshkent, Yunusobod", 4, 120, "yard", "interior", "Zamonaviy"),
            (0, "Samarqand, Registon", 3, 85, "apartment", "architecture", None),
            (1, "Toshkent, Chilonzor", 6, 200, "office", "interior", "Xay-tek"),
            (1, "Buxoro", 5, 160, "restaurant", "interior", "own:Sharqona"),
            (2, "Toshkent, Mirzo Ulug'bek", 8, 450, "wedding_hall", "architecture", None),
            (2, "Andijon", 5, 240, "yard", "architecture", "Klassik"),
            (3, "Toshkent, Sergeli", 3, 70, "apartment", "interior", "Loft"),
            (3, "Namangan", 4, 150, "yard", "interior", None),
        ]
        orders = []
        for owner_i, place, rooms, size, obj, service, style in spec:
            low, high = estimate_price(size, obj, service, rooms, place)
            orders.append(Application.objects.create(
                owner=clients[owner_i], location=place, rooms_count=rooms, size_m2=size, object_type=obj,
                service_type=service, description=ORDER_TEXTS[obj], plan_pdf="plans/uy.jpg",
                interior_style=styles.get(style) if style and not style.startswith("own:") else None,
                custom_style=style[4:] if style and style.startswith("own:") else "",
                estimate_min=low, estimate_max=high,
            ))
        A = Offer.Source.ARCHITECT_APPLIED
        I = Offer.Source.USER_INVITED
        s1, s2, s3 = studios
        f1, f2, f3, f4, f5 = freelancers

        # 1: three architects applied, waiting for the client
        for who in (f1, s1, f2):
            send_offer(orders[0], who, A)
        # 2: accepted by the client
        accept_offer(send_offer(orders[1], f3, A))
        # 3: a studio's application accepted -> assigned to a worker, deadline already passed
        offer = send_offer(orders[2], s2, A)
        accept_offer(offer)
        assign_worker(offer.studio_assignment, workers[1][0], deadline=date.today() - timedelta(days=3))
        # 4: the client invited a studio (waiting for the studio's answer)
        send_offer(orders[3], s1, I)
        # 5: a studio accepted the client's invitation; one worker took it and is working on it
        offer = send_offer(orders[4], s3, I)
        accept_invitation(offer)
        claim_assignment(offer.studio_assignment, workers[2][1])
        offer.studio_assignment.refresh_from_db()
        from offers.services import set_deadline
        set_deadline(offer.studio_assignment, date.today() + timedelta(days=9))
        # 6: an invitation and an application at the same time
        send_offer(orders[5], f2, I)
        send_offer(orders[5], f4, A)
        # 7: finished and closed
        offer = send_offer(orders[6], f5, A)
        accept_offer(offer)
        complete_offer(offer)
        # 8: still open, no offers: architects can apply live while trying the site

        # a second studio order that is finished by a worker, and one nobody has taken yet
        extra = Application.objects.create(
            owner=clients[2], location="Toshkent, Yakkasaroy", rooms_count=3, size_m2=90, object_type="apartment",
            service_type="architecture", description="Kvartira planirovkasi o'zgarishi.", plan_pdf="plans/uy.jpg",
            estimate_min=350, estimate_max=650,
        )
        offer = send_offer(extra, s1, A)
        accept_offer(offer)
        assign_worker(offer.studio_assignment, workers[0][0], deadline=date.today() + timedelta(days=5))
        mark_assignment_done(offer.studio_assignment)

        self.stdout.write(self.style.SUCCESS("Demo data created. Password for everyone: " + PASSWORD + " (clients: phone only)."))
        self.stdout.write("\nSTUDIOS (phone + password)")
        for phone, name, person, *_ in STUDIOS:
            self.stdout.write(f"  {phone}  {name}  ({person})")
        self.stdout.write("\nWORKERS")
        for index, ws in EMPLOYEES.items():
            for phone, name, _ in ws:
                self.stdout.write(f"  {phone}  {name}  — {STUDIOS[index][1]}")
        self.stdout.write("\nFREELANCERS")
        for phone, name, *_ in FREELANCERS:
            self.stdout.write(f"  {phone}  {name}")
        self.stdout.write("\nCLIENTS (phone only)")
        for phone, first, last in CLIENTS:
            self.stdout.write(f"  {phone}  {first} {last}")
