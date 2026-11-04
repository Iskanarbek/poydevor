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


class BellAndListTests(Base):
    def test_bell_shows_the_unread_count_and_opening_marks_read(self):
        send_offer(self.application, self.freelancer, source=Offer.Source.USER_INVITED)
        self.client.force_login(self.freelancer.user)
        page = self.client.get(reverse("notifications:list"))
        self.assertEqual(page.context["unread_notifications_count"], 1)
        n = Notification.objects.get(user=self.freelancer.user)
        response = self.client.get(reverse("notifications:open", args=[n.pk]))
        self.assertRedirects(response, n.url, fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_all_read(self):
        for i in range(3):
            Notification.objects.create(user=self.client_user, text=f"t{i}")
        self.client.force_login(self.client_user)
        self.client.post(reverse("notifications:mark_all_read"))
        self.assertFalse(Notification.objects.filter(user=self.client_user, is_read=False).exists())

    def test_nobody_can_open_someone_elses_notification(self):
        n = Notification.objects.create(user=self.client_user, text="secret")
        self.client.force_login(self.freelancer.user)
        self.assertEqual(self.client.get(reverse("notifications:open", args=[n.pk])).status_code, 404)

    def test_an_outside_address_is_never_followed(self):
        n = Notification.objects.create(user=self.client_user, text="x", url="https://evil.example/")
        self.client.force_login(self.client_user)
        self.assertRedirects(self.client.get(reverse("notifications:open", args=[n.pk])), reverse("notifications:list"), fetch_redirect_response=False)
