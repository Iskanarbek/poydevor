"""One long walk through the whole product, the way real people use it, using only the site's
own pages and forms (no shortcuts through the database, except for the admin's account)."""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile, Style
from notifications.models import Notification
from offers.models import Offer, StudioAssignment


def jpeg(name="a.jpg", colour="blue"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def pdf(name="reja.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF", content_type="application/pdf")


class FullJourneyTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="poydevor-journey-")
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        Style.objects.create(name="Loft")
        Style.objects.create(name="Klassik")

    # -- small helpers ------------------------------------------------------------------------

    def new_visitor(self):
        self.client.logout()

    def log_in(self, phone, password=""):
        return self.client.post(reverse("accounts:login"), {"phone": phone, "password": password})

    def unread(self, phone):
        return list(Notification.objects.filter(user__phone=phone, is_read=False).values_list("text", flat=True))

    def add_portfolio(self, count):
        loft = Style.objects.get(name="Loft")
        for i in range(count):
            response = self.client.post(reverse("architects:project_create"), {
                "title": f"Loyiha {i}", "object_type": "yard", "service_type": "interior", "style": loft.pk,
                "price_usd": 1000 + i, "description": "Uy ichi to'liq qayta ishlandi.", "images": [jpeg(f"p{i}.jpg")],
            })
            self.assertEqual(response.status_code, 302, response.content[:300])

    # -- the journey -------------------------------------------------------------------------

    def test_everyone_uses_the_whole_site(self):
        # 1. A studio registers: logo, name, year, responsible person with birth date, Telegram, password.
        page = self.client.get(reverse("architects:register_studio"))
        for needed in ("Studiya logotipi", "ilgan sanasi", "Parolni takrorlang"):
            self.assertContains(page, needed)
        for gone in ('name="email"', 'name="founders"', 'name="staff_count"', 'name="projects_count"'):
            self.assertNotContains(page, gone)
        response = self.client.post(reverse("architects:register_studio"), {
            "avatar": jpeg("logo.jpg", "red"), "studio_name": "ArcDes", "founded_year": 2018,
            "responsible_person": "Alisher Qodirov", "responsible_birth_date": "1990-03-04", "phone": "+998 90 111 11 11",
            "telegram_username": "@arcdes", "password": "1", "password_confirm": "1",
        })
        self.assertRedirects(response, reverse("architects:studio_dashboard"), fetch_redirect_response=False)
        studio_owner = ArchitectProfile.objects.get(user__phone="+998901111111")
        self.assertEqual(studio_owner.display_name, "ArcDes")
        self.assertEqual(studio_owner.wallet.balance, 2)
        self.assertNotContains(self.client_class().get(reverse("architects:register_freelancer")), 'name="projects_count"')
        self.add_portfolio(10)

        # 2. A freelancer registers (no Telegram: optional), builds a portfolio with a style of their own.
        self.new_visitor()
        response = self.client.post(reverse("architects:register_freelancer"), {
            "full_name": "Jasur Axmedov", "birth_year": 1994, "phone": "+998 90 222 22 22", "telegram_username": "",
            "password": "pw", "password_confirm": "pw",
        })
        self.assertEqual(response.status_code, 302)
        freelancer = ArchitectProfile.objects.get(user__phone="+998902222222")
        response = self.client.post(reverse("architects:project_create"), {
            "title": "Skandinav uy", "object_type": "apartment", "service_type": "architecture",
            "style": "other", "custom_style": "Skandinav", "price_usd": 800, "images": [jpeg()],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(freelancer.projects.get().style_label, "Skandinav")
        self.add_portfolio(4)

        # 3. The admin verifies both portfolios; the architects hear about it.
        admin = User.objects.create_superuser(phone="+998900000001", password="x", first_name="A", last_name="D", role="architect")
        self.client.force_login(admin)
        for profile in (studio_owner, freelancer):
            self.client.post(reverse("staff_architect_verify", args=[profile.pk]))
        self.assertTrue(any("tasdiqlandi" in t for t in self.unread("+998901111111")))
        self.assertTrue(any("tasdiqlandi" in t for t in self.unread("+998902222222")))

        # 4. An employee asks to join the studio; the owner is notified and accepts.
        self.new_visitor()
        self.client.post(reverse("architects:register_employee"), {
            "full_name": "Sardor Murodov", "birth_year": 1998, "phone": "+998 90 333 33 33", "telegram_username": "sardor_m",
            "password": "e", "password_confirm": "e", "studio": studio_owner.studio_owned.pk,
        })
        employee = ArchitectProfile.objects.get(user__phone="+998903333333")
        self.assertTrue(any("qo'shilmoqchi" in t for t in self.unread("+998901111111")))
        self.log_in("+998901111111", "1")
        self.client.post(reverse("architects:employee_decision", args=[employee.pk]), {"decision": "accept"})
        self.assertTrue(any("qabul qildi" in t for t in self.unread("+998903333333")))

        # 5. A client signs up (phone only) and posts an order: it is saved but nobody sees it yet.
        self.new_visitor()
        self.client.post(reverse("accounts:signup"), {"first_name": "Aziz", "last_name": "Karimov", "phone": "+998 90 444 44 44"})
        self.assertEqual(User.objects.get(phone="+998904444444").role, "user")
        incomplete = self.client.post(reverse("applications:post"), {"size_m2": 120})
        self.assertEqual(incomplete.status_code, 200)
        form_page = self.client.get(reverse("applications:post"))
        self.assertNotContains(form_page, "avtomatik")
        self.assertNotContains(form_page, "Byudjet")
        response = self.client.post(reverse("applications:post"), {
            "size_m2": 120, "object_type": "yard", "service_type": ["architecture", "interior"], "rooms_count": 4,
            "location": "Toshkent, Yunusobod", "interior_style": "other", "custom_style": "Art-deko",
            "files": [jpeg("uy1.jpg"), jpeg("uy2.jpg"), pdf("kadastr.pdf")], "price_confirmed": "on",
        })
        public_order = Application.objects.get()
        self.assertRedirects(response, reverse("applications:choose", args=[public_order.pk]), fetch_redirect_response=False)
        self.assertEqual(public_order.files.count(), 3)
        self.assertEqual((public_order.service_type, public_order.estimate_min, public_order.style_label), ("both", 2350, "Art-deko"))
        self.assertEqual(public_order.publication, "draft")
        # leaving and coming back lands on the same two questions
        self.assertRedirects(self.client.get(reverse("applications:detail", args=[public_order.pk])), reverse("applications:choose", args=[public_order.pk]), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("applications:choose", args=[public_order.pk])), "Hammaga ochiq qilish")
        # still invisible to architects...
        self.new_visitor()
        self.log_in("+998902222222", "pw")
        self.assertNotContains(self.client.get(reverse("architects:freelancer_dashboard") + "?tab=market"), "Toshkent, Yunusobod")
        # ...until the client opens it to everyone
        self.new_visitor()
        self.log_in("+998904444444")
        self.client.post(reverse("applications:choose", args=[public_order.pk]), {"audience": "public"})
        home = self.client.get(reverse("applications:dashboard"))
        self.assertContains(home, "Buyurtma yaratish")
        self.assertContains(home, "Loyiha 0")                        # the architects' projects are on the home page
        self.assertContains(home, "$1000")                            # ...with their prices
        self.assertContains(home, "Hovli / Uchastka")
        self.assertContains(home, "Skandinav")                        # ...and the architect's own style
        # a second order goes to ONE chosen studio instead
        self.client.post(reverse("applications:post"), {
            "size_m2": 90, "object_type": "wedding_hall", "service_type": "architecture", "rooms_count": 2,
            "location": "Samarqand", "price_confirmed": "on",
        })
        order = Application.objects.get(location="Samarqand")
        self.client.get(reverse("applications:pick_architect", args=[order.pk]))
        self.assertContains(self.client.get(reverse("architects:list")), "e'loni yuborish uchun")
        self.client.post(reverse("offers:send", args=[studio_owner.pk]), {"application": order.pk})
        order.refresh_from_db()
        self.assertEqual((order.publication, order.sent_to), ("direct", studio_owner))
        self.assertTrue(any("sizga loyiha yubordi" in t for t in self.unread("+998901111111")))

        # 6. The freelancer sees the public order (1 coin to apply); the client is notified. The direct order stays hidden.
        self.new_visitor()
        self.log_in("+998902222222", "pw")
        market = self.client.get(reverse("architects:freelancer_dashboard") + "?tab=market")
        self.assertContains(market, "Toshkent, Yunusobod")
        self.assertNotContains(market, "Samarqand")
        self.assertContains(market, "$2350–4250")
        applied = self.client.post(reverse("offers:architect_apply", args=[public_order.pk]))
        self.assertEqual(applied.status_code, 302)
        freelancer.wallet.refresh_from_db()
        self.assertEqual(freelancer.wallet.balance, 1)
        self.assertTrue(any("ariza yubordi" in t for t in self.unread("+998904444444")))
        self.assertEqual(self.client.get(reverse("offers:architect_apply", args=[order.pk])).status_code, 404)

        # 7. The studio accepts the invitation (2 coins); the employee is told about the new order.
        self.new_visitor()
        self.log_in("+998901111111", "1")
        invitation = Offer.objects.get(architect=studio_owner)
        self.client.post(reverse("offers:respond", args=[invitation.pk]), {"decision": "accept"})
        studio_owner.wallet.refresh_from_db()
        self.assertEqual(studio_owner.wallet.balance, 0)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, Offer.Status.ACCEPTED)
        self.assertTrue(any("Studiyaga yangi buyurtma" in t for t in self.unread("+998903333333")))
        self.assertTrue(any("taklifingizni qabul qildi" in t for t in self.unread("+998904444444")))

        # 8. The studio sees it on its orders page, labelled as sent by the client, and hands it to the employee.
        orders = self.client.get(reverse("architects:studio_dashboard") + "?tab=orders")
        self.assertContains(orders, "Mijoz sizga yubordi")
        assignment = StudioAssignment.objects.get()
        self.client.post(reverse("architects:assignment_assign", args=[assignment.pk]), {"worker": employee.pk, "deadline": "2030-05-01"})
        self.assertTrue(any("biriktirildi" in t and "01.05.2030" in t for t in self.unread("+998903333333")))

        # 9. The employee logs in (needs the password), opens the bell, does the job.
        self.new_visitor()
        self.assertEqual(self.log_in("+998903333333", "").status_code, 200)       # no password: refused, asked for it
        self.assertEqual(self.log_in("+998903333333", "e").status_code, 302)
        panel = self.client.get(reverse("architects:employee_workspace"))
        self.assertTrue(any("Sizga buyurtma biriktirildi" in t for t in panel.context["new_here"]))   # the news shows on the tab
        self.assertNotIn("tasks", panel.context["tab_badges"])            # opened, so no red number on it any more
        self.assertIn("open", panel.context["tab_badges"])               # (the new-orders tab still has its own)
        self.client.post(reverse("architects:assignment_done", args=[assignment.pk]))
        self.assertTrue(any("bajardi" in t for t in self.unread("+998901111111")))

        # 10. The client sees the studio's logo/name and contacts, then closes the project.
        self.new_visitor()
        self.log_in("+998904444444")
        detail = self.client.get(reverse("applications:detail", args=[order.pk]))
        self.assertContains(detail, "ArcDes")
        self.assertContains(detail, "tel:+998901111111")
        self.assertContains(detail, "https://t.me/arcdes")
        self.client.post(reverse("offers:complete", args=[invitation.pk]))
        self.assertTrue(any("yakunlandi" in t for t in self.unread("+998901111111")))

        # 11. Nothing about orders expiring anywhere; account switching and unknown pages behave.
        for url in (reverse("applications:dashboard"), reverse("applications:detail", args=[order.pk])):
            page = self.client.get(url)
            self.assertNotContains(page, "avtomatik o'chiril")
            self.assertNotContains(page, "Hali ham izlayapman")
        target = reverse("applications:dashboard")
        self.new_visitor()
        self.assertRedirects(self.client.get(target), f"{reverse('accounts:login')}?next={target}", fetch_redirect_response=False)
        self.assertRedirects(self.log_in("+998904444444"), reverse("dashboard"), fetch_redirect_response=False)
        missing = self.client.get("/yoq-sahifa/")
        self.assertEqual(missing.status_code, 404)
        self.assertContains(missing, "Bosh sahifaga qaytish", status_code=404)
