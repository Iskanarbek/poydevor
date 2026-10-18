from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile, Studio
from offers.models import Offer, StudioAssignment
from offers.services import (
    AssignmentAlreadyTakenError,
    WorkerNotInStudioError,
    accept_offer,
    assign_worker,
    claim_assignment,
    mark_assignment_done,
    send_offer,
)
from wallet.models import Wallet
from wallet.services import topup_coins

Kind = ArchitectProfile.Kind


def make_studio(name="ArcDes"):
    owner_user = User.objects.create_user(
        phone=f"+998901{abs(hash(name)) % 1000000:06d}", password="x",
        first_name=name, last_name="Owner", role=User.Role.ARCHITECT,
    )
    owner = ArchitectProfile.objects.create(user=owner_user, kind=Kind.STUDIO_OWNER)
    Studio.objects.create(
        owner=owner, name=name, founded_on="2020-01-01", founders="X", responsible_person="X",
        responsible_birth_date="1990-01-01", email="s@s.uz", phone="+998901234567",
        staff_count=5, projects_count=5,
    )
    wallet = Wallet.objects.create(architect=owner)
    topup_coins(wallet, 100)
    return owner


def make_employee(studio, name="Worker"):
    user = User.objects.create_user(
        phone=f"+998902{abs(hash(name)) % 1000000:06d}", password="x",
        first_name=name, last_name="E", role=User.Role.ARCHITECT,
    )
    return ArchitectProfile.objects.create(user=user, kind=Kind.STUDIO_EMPLOYEE, studio=studio.studio_owned)


class StudioAssignmentCreationTests(TestCase):
    def setUp(self):
        client_user = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=client_user, rooms_count=3, location="Toshkent")
        self.owner = make_studio()

    def test_accepting_a_studio_offer_creates_an_open_assignment(self):
        offer = send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        assignment = StudioAssignment.objects.get(offer=offer)
        self.assertEqual(assignment.status, StudioAssignment.Status.OPEN)
        self.assertIsNone(assignment.worker)

    def test_a_freelancer_offer_gets_no_assignment(self):
        freelancer_user = User.objects.create_user(
            phone="+998903333333", password="x", first_name="Solo", last_name="F", role=User.Role.ARCHITECT,
        )
        freelancer = ArchitectProfile.objects.create(user=freelancer_user)
        Wallet.objects.create(architect=freelancer, balance=10)
        offer = send_offer(self.application, freelancer, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        self.assertFalse(StudioAssignment.objects.filter(offer=offer).exists())


class AssignmentWorkflowTests(TestCase):
    def setUp(self):
        client_user = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=client_user, rooms_count=3, location="Toshkent")
        self.owner = make_studio()
        self.worker1 = make_employee(self.owner, "Worker1")
        self.worker2 = make_employee(self.owner, "Worker2")
        offer = send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        self.assignment = StudioAssignment.objects.get(offer=offer)

    def test_an_employee_can_claim_an_open_order(self):
        claim_assignment(self.assignment, self.worker1)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, StudioAssignment.Status.ASSIGNED)
        self.assertEqual(self.assignment.worker, self.worker1)

    def test_a_second_employee_cannot_claim_an_already_claimed_order(self):
        claim_assignment(self.assignment, self.worker1)
        with self.assertRaises(AssignmentAlreadyTakenError):
            claim_assignment(self.assignment, self.worker2)

    def test_owner_can_assign_directly_with_a_deadline(self):
        assign_worker(self.assignment, self.worker2, deadline="2030-01-01")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.worker, self.worker2)
        self.assertEqual(str(self.assignment.deadline), "2030-01-01")

    def test_owner_can_reassign_to_someone_else(self):
        claim_assignment(self.assignment, self.worker1)
        assign_worker(self.assignment, self.worker2)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.worker, self.worker2)

    def test_cannot_assign_a_worker_from_another_studio(self):
        other_owner = make_studio("OtherStudio")
        outsider = make_employee(other_owner, "Outsider")
        with self.assertRaises(WorkerNotInStudioError):
            assign_worker(self.assignment, outsider)

    def test_marking_done_frees_the_worker(self):
        claim_assignment(self.assignment, self.worker1)
        mark_assignment_done(self.assignment)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, StudioAssignment.Status.DONE)
        self.assertIsNotNone(self.assignment.done_at)

    def test_overdue_flag(self):
        assign_worker(self.assignment, self.worker1, deadline="2000-01-01")
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_overdue)
        mark_assignment_done(self.assignment)
        self.assertFalse(self.assignment.is_overdue)


class StudioOrdersViewTests(TestCase):
    def setUp(self):
        client_user = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=client_user, rooms_count=3, location="Toshkent")
        self.owner = make_studio()
        self.worker = make_employee(self.owner, "Worker1")
        offer = send_offer(self.application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        self.assignment = StudioAssignment.objects.get(offer=offer)

    def test_owner_sees_the_orders_tab(self):
        self.client.force_login(self.owner.user)
        page = self.client.get("/studio/dashboard/?tab=orders")
        self.assertContains(page, "Toshkent")
        self.assertContains(page, "Bo'sh — keyingi ishga tayyor")

    def test_employee_can_claim_from_their_workspace(self):
        self.client.force_login(self.worker.user)
        response = self.client.post(f"/employee/buyurtmalar/{self.assignment.pk}/olish/")
        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.worker, self.worker)

    def test_employee_can_mark_their_own_order_done(self):
        self.client.force_login(self.worker.user)
        self.client.post(f"/employee/buyurtmalar/{self.assignment.pk}/olish/")
        response = self.client.post(f"/employee/buyurtmalar/{self.assignment.pk}/bajarildi/")
        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, StudioAssignment.Status.DONE)

    def test_owner_can_assign_via_the_form(self):
        self.client.force_login(self.owner.user)
        response = self.client.post(
            f"/studio/buyurtmalar/{self.assignment.pk}/biriktirish/",
            {"worker": self.worker.pk, "deadline": "2030-06-15"},
        )
        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.worker, self.worker)
        self.assertEqual(str(self.assignment.deadline), "2030-06-15")
