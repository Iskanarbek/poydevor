from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile, Studio
from notifications.models import Notification
from offers.models import Offer, StudioAssignment
from offers.services import accept_invitation, accept_offer, assign_worker, claim_assignment, complete_offer, mark_assignment_done, reject_offer, send_offer, set_deadline
from wallet.models import Wallet

Kind = ArchitectProfile.Kind


def texts(user):
    return list(Notification.objects.filter(user=user).values_list("text", flat=True))


class Base(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(phone="+998901111111", first_name="Aziz", last_name="K", role=User.Role.USER)
        self.application = Application.objects.create(owner=self.client_user, rooms_count=3, location="Toshkent")
        owner_user = User.objects.create_user(phone="+998902222222", first_name="Own", last_name="Er", role=User.Role.ARCHITECT)
        self.owner = ArchitectProfile.objects.create(user=owner_user, kind=Kind.STUDIO_OWNER)
        self.studio = Studio.objects.create(
            owner=self.owner, name="ArcDes", founded_on="2020-01-01", responsible_person="X", phone="+998901234567", projects_count=1,
        )
        Wallet.objects.create(architect=self.owner, balance=10)
        w_user = User.objects.create_user(phone="+998903333333", first_name="Work", last_name="Er", role=User.Role.ARCHITECT)
        self.worker = ArchitectProfile.objects.create(user=w_user, kind=Kind.STUDIO_EMPLOYEE, studio=self.studio)
        free_user = User.objects.create_user(phone="+998904444444", first_name="Solo", last_name="F", role=User.Role.ARCHITECT)
        self.freelancer = ArchitectProfile.objects.create(user=free_user)
        Wallet.objects.create(architect=self.freelancer, balance=10)


class OfferNotificationTests(Base):
    def test_client_inviting_an_architect_notifies_the_architect(self):
        send_offer(self.application, self.freelancer, source=Offer.Source.USER_INVITED)
        self.assertTrue(any("sizga loyiha yubordi" in t for t in texts(self.freelancer.user)))

    def test_architect_applying_notifies_the_client(self):
        send_offer(self.application, self.freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        self.assertTrue(any("ariza yubordi" in t for t in texts(self.client_user)))
        n = Notification.objects.get(user=self.client_user)
        self.assertEqual(n.url, reverse("applications:detail", args=[self.application.pk]))

    def test_client_accepting_and_rejecting_notify_the_architect(self):
        offer = send_offer(self.application, self.freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        self.assertTrue(any("qabul qilindi" in t for t in texts(self.freelancer.user)))
        other = send_offer(Application.objects.create(owner=self.client_user, rooms_count=1, location="Buxoro"),
                           self.freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        reject_offer(other)
        self.assertTrue(any("rad etildi" in t for t in texts(self.freelancer.user)))

    def test_losers_are_told_when_the_client_picks_someone_else(self):
        a = send_offer(self.application, self.freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(a)
        self.assertTrue(any("boshqa arxitektorni tanladi" in t for t in texts(self.owner.user)))

    def test_architect_accepting_an_invitation_notifies_the_client(self):
        offer = send_offer(self.application, self.freelancer, source=Offer.Source.USER_INVITED)
        accept_invitation(offer)
        self.assertTrue(any("taklifingizni qabul qildi" in t for t in texts(self.client_user)))

    def test_completing_notifies_the_architect(self):
        offer = send_offer(self.application, self.freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        complete_offer(offer)
        self.assertTrue(any("yakunlandi" in t for t in texts(self.freelancer.user)))


class StudioNotificationTests(Base):
    def test_a_studio_win_tells_every_approved_employee(self):
        self.worker.approval_status = ArchitectProfile.ApprovalStatus.APPROVED
        self.worker.save()
        offer = send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        self.assertTrue(any("Studiyaga yangi buyurtma" in t for t in texts(self.worker.user)))

    def test_assigning_claiming_deadline_and_done(self):
        self.worker.approval_status = ArchitectProfile.ApprovalStatus.APPROVED
        self.worker.save()
        offer = send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        assignment = StudioAssignment.objects.get(offer=offer)
        assign_worker(assignment, self.worker, deadline="2030-01-05")
        self.assertTrue(any("biriktirildi" in t and "05.01.2030" in t for t in texts(self.worker.user)))
        set_deadline(assignment, "2030-02-01")
        self.assertTrue(any("muddati" in t for t in texts(self.worker.user)))
        mark_assignment_done(assignment)
        self.assertTrue(any("bajardi" in t for t in texts(self.owner.user)))

    def test_claiming_tells_the_studio(self):
        self.worker.approval_status = ArchitectProfile.ApprovalStatus.APPROVED
        self.worker.save()
        offer = send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        claim_assignment(StudioAssignment.objects.get(offer=offer), self.worker)
        self.assertTrue(any("buyurtmani oldi" in t for t in texts(self.owner.user)))

    def test_a_new_employee_request_notifies_the_studio_owner_and_the_decision_notifies_the_employee(self):
        self.client.post(reverse("architects:register_employee"), {
            "full_name": "Sardor Murodov", "birth_year": 1998, "phone": "+998 93 987 65 43", "password": "1",
            "password_confirm": "1", "studio": self.studio.pk,
        })
        self.assertTrue(any("qo'shilmoqchi" in t for t in texts(self.owner.user)))
        employee = ArchitectProfile.objects.get(user__phone="+998939876543")
        self.client.force_login(self.owner.user)
        self.client.post(reverse("architects:employee_decision", args=[employee.pk]), {"decision": "accept"})
        self.assertTrue(any("qabul qildi" in t for t in texts(employee.user)))


class SectionBadgeTests(Base):
    """No notifications page: the news shows as a red number on the tab / order it belongs to."""

    def test_a_tab_gets_a_number_until_it_is_opened(self):
        send_offer(self.application, self.freelancer, source=Offer.Source.USER_INVITED)
        self.client.force_login(self.freelancer.user)
        page = self.client.get("/freelancer/dashboard/?tab=room")
        self.assertEqual(page.context["tab_badges"], {"orders": 1})
        self.assertContains(page, 'data-badge="orders"')
        orders = self.client.get("/freelancer/dashboard/?tab=orders")
        self.assertEqual(len(orders.context["new_here"]), 1)              # the news is shown on the tab itself
        self.assertContains(orders, "sizga loyiha yubordi")
        again = self.client.get("/freelancer/dashboard/?tab=orders")
        self.assertEqual((again.context["new_here"], again.context["tab_badges"]), ([], {}))   # ...once

    def test_there_is_no_notifications_page_or_bell(self):
        self.assertEqual(self.client.get("/bildirishnomalar/").status_code, 404)
        self.client.force_login(self.client_user)
        self.assertNotContains(self.client.get(reverse("applications:dashboard")), "Bildirishnomalar")

    def test_clients_see_a_number_on_the_order_and_it_clears_when_the_order_is_opened(self):
        send_offer(self.application, self.freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        self.client.force_login(self.client_user)
        home = self.client.get(reverse("applications:dashboard"))
        self.assertEqual(home.context["order_badges"], {self.application.pk: 1})
        self.assertContains(home, f'data-order-badge="{self.application.pk}"')
        detail = self.client.get(reverse("applications:detail", args=[self.application.pk]))
        self.assertContains(detail, "ariza yubordi")
        self.assertEqual(self.client.get(reverse("applications:dashboard")).context["order_badges"], {})

    def test_the_menu_shows_the_total(self):
        send_offer(self.application, self.freelancer, source=Offer.Source.USER_INVITED)
        self.client.force_login(self.freelancer.user)
        self.assertContains(self.client.get("/freelancer/dashboard/?tab=room"), 'data-nav-badge="1"')
