from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile, Studio
from notifications.models import Notification
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
        responsible_birth_date="1990-01-01", phone="+998901234567",
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


class EmployeePanelTests(TestCase):
    """The employee's home is the same panel layout as a studio's or freelancer's."""

    def setUp(self):
        client_user = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.owner = make_studio()
        self.worker = make_employee(self.owner, "Worker1")
        self.other = make_employee(self.owner, "Worker2")
        self.assignments = []
        for place in ("Toshkent", "Samarqand", "Buxoro"):
            application = Application.objects.create(owner=client_user, rooms_count=3, location=place)
            offer = send_offer(application, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
            accept_offer(offer)
            self.assignments.append(StudioAssignment.objects.get(offer=offer))
        self.client.force_login(self.worker.user)

    def page(self, tab=None):
        return self.client.get("/employee/workspace/" + (f"?tab={tab}" if tab else ""))

    def test_uses_the_shared_panel_with_a_tab_bar_and_stats(self):
        page = self.page()
        self.assertTemplateUsed(page, "architects/workspace.html")
        for label in ("Mening ishlarim", "Ochiq buyurtmalar", "Bajarilgan ishlar", "Studiya"):
            self.assertContains(page, label)
        self.assertEqual(page.context["tab"], "tasks")
        self.assertEqual(page.context["emp_stats"], {"active": 0, "overdue": 0, "done": 0, "open": 3})

    def test_unknown_tab_falls_back_to_my_jobs(self):
        self.assertEqual(self.page("nonsense").context["tab"], "tasks")

    def test_open_tab_lists_unclaimed_orders_with_a_claim_button(self):
        page = self.page("open")
        for place in ("Toshkent", "Samarqand", "Buxoro"):
            self.assertContains(page, place)
        self.assertContains(page, "Men olaman")
        self.assertContains(page, f"/employee/buyurtmalar/{self.assignments[0].pk}/olish/")

    def test_claimed_job_moves_to_my_jobs_and_leaves_the_open_list(self):
        self.client.post(f"/employee/buyurtmalar/{self.assignments[0].pk}/olish/")
        mine = self.page("tasks")
        self.assertContains(mine, "Toshkent")
        self.assertContains(mine, "Bajarildi")
        self.assertEqual(mine.context["emp_stats"]["active"], 1)
        open_places = [a.offer.application.location for a in self.page("open").context["open_assignments"]]
        self.assertNotIn("Toshkent", open_places)

    def test_overdue_job_is_flagged_and_listed_first(self):
        assign_worker(self.assignments[0], self.worker, deadline="2099-01-01")
        assign_worker(self.assignments[1], self.worker, deadline="2000-01-01")
        assign_worker(self.assignments[2], self.worker)
        page = self.page("tasks")
        order = [a.offer.application.location for a in page.context["my_assignments"]]
        self.assertEqual(order, ["Samarqand", "Toshkent", "Buxoro"])
        self.assertEqual(page.context["emp_stats"]["overdue"], 1)
        self.assertContains(page, "Muddati o'tgan")

    def test_finishing_a_job_lands_on_the_done_tab(self):
        self.client.post(f"/employee/buyurtmalar/{self.assignments[0].pk}/olish/")
        response = self.client.post(f"/employee/buyurtmalar/{self.assignments[0].pk}/bajarildi/")
        self.assertRedirects(response, "/employee/workspace/?tab=done", fetch_redirect_response=False)
        done = self.page("done")
        self.assertContains(done, "Toshkent")
        self.assertEqual(done.context["emp_stats"]["done"], 1)

    def test_other_employees_jobs_are_not_shown_as_mine(self):
        assign_worker(self.assignments[0], self.other)
        self.assertNotContains(self.page("tasks"), "Toshkent")

    def test_studio_tab_shows_the_studio_and_the_team(self):
        page = self.page("studio")
        self.assertContains(page, "ArcDes")
        self.assertContains(page, "Worker2")
        self.assertContains(page, "Siz")

    def test_deadline_days_left(self):
        assign_worker(self.assignments[0], self.worker, deadline="2000-01-01")
        self.assignments[0].refresh_from_db()
        self.assertLess(self.assignments[0].days_left, 0)
        self.assertIsNone(self.assignments[1].days_left)


class StudioOrdersTableTests(TestCase):
    """One table for everything the studio applied for / was invited to, with assigning,
    reassigning, deadlines and the "Yakunlash" button."""

    def setUp(self):
        self.client_user = User.objects.create_user(phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER)
        self.owner = make_studio()
        self.worker1 = make_employee(self.owner, "Worker1")
        self.worker2 = make_employee(self.owner, "Worker2")
        for w in (self.worker1, self.worker2):
            w.approval_status = ArchitectProfile.ApprovalStatus.APPROVED
            w.save()
        self.client.force_login(self.owner.user)

    def order(self, place):
        return Application.objects.create(owner=self.client_user, rooms_count=3, location=place)

    def table(self):
        return self.client.get("/studio/dashboard/?tab=orders")

    def test_there_is_no_separate_ongoing_tab_and_no_stray_template_text(self):
        page = self.table()
        self.assertNotContains(page, "Davom etayotgan ishlar")
        self.assertNotContains(page, "{#")
        self.assertNotContains(page, "monitoring table")

    def test_every_state_shows_in_the_one_table(self):
        waiting = send_offer(self.order("Samarqand"), self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        invited = send_offer(self.order("Buxoro"), self.owner, source=Offer.Source.USER_INVITED)
        accepted = send_offer(self.order("Toshkent"), self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(accepted)
        page = self.table()
        for text in ("Samarqand", "Buxoro", "Toshkent", "Mijoz javobi kutilmoqda", "Javobingiz kutilmoqda", "xodim tanlang"):
            self.assertContains(page, text)
        self.assertEqual(len(page.context["order_rows"]), 3)

    def test_assign_set_deadline_reassign_and_the_old_worker_loses_the_job(self):
        offer = send_offer(self.order("Toshkent"), self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        assignment = StudioAssignment.objects.get(offer=offer)
        url = f"/studio/buyurtmalar/{assignment.pk}/biriktirish/"
        self.client.post(url, {"worker": self.worker1.pk, "deadline": "2030-06-01"})
        self.client.force_login(self.worker1.user)
        self.assertContains(self.client.get("/employee/workspace/?tab=tasks"), "Toshkent")
        # the owner changes the deadline, then hands the job to the other worker
        self.client.force_login(self.owner.user)
        self.client.post(url, {"deadline": "2030-07-01"})
        assignment.refresh_from_db()
        self.assertEqual((str(assignment.deadline), assignment.worker), ("2030-07-01", self.worker1))
        self.client.post(url, {"worker": self.worker2.pk, "deadline": "2030-07-15"})
        self.client.force_login(self.worker1.user)
        mine = self.client.get("/employee/workspace/?tab=tasks")
        self.assertEqual(list(mine.context["my_assignments"]), [])                                # it disappeared
        self.assertTrue(Notification.objects.filter(user=self.worker1.user, text__contains="boshqa xodimga").exists())
        self.client.force_login(self.worker2.user)
        self.assertContains(self.client.get("/employee/workspace/?tab=tasks"), "Toshkent")       # the new one sees it

    def test_finish_button_moves_the_project_to_finished_and_tells_the_client(self):
        offer = send_offer(self.order("Toshkent"), self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        assignment = StudioAssignment.objects.get(offer=offer)
        self.client.post(f"/studio/buyurtmalar/{assignment.pk}/biriktirish/", {"worker": self.worker1.pk})
        response = self.client.post(f"/ariza/{offer.pk}/arxitektor-yakunlash/")
        self.assertRedirects(response, "/studio/dashboard/?tab=finished", fetch_redirect_response=False)
        offer.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual((offer.status, assignment.status), (Offer.Status.COMPLETED, StudioAssignment.Status.DONE))
        self.assertContains(self.client.get("/studio/dashboard/?tab=finished"), "Toshkent")
        self.assertEqual(self.client.get("/studio/dashboard/?tab=orders").context["order_rows"], [])   # no longer in the working table
        self.assertTrue(Notification.objects.filter(user=self.client_user, text__contains="yakunladi").exists())

    def test_only_the_owner_of_an_accepted_offer_can_finish_it(self):
        offer = send_offer(self.order("Toshkent"), self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        self.assertEqual(self.client.post(f"/ariza/{offer.pk}/arxitektor-yakunlash/").status_code, 404)   # not accepted yet
        accept_offer(offer)
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.post(f"/ariza/{offer.pk}/arxitektor-yakunlash/").status_code, 404)   # someone else

    def test_a_freelancer_can_finish_from_their_table_too(self):
        from offers.models import Offer as O
        free_user = User.objects.create_user(phone="+998909998877", password="x", first_name="Solo", last_name="F", role=User.Role.ARCHITECT)
        free = ArchitectProfile.objects.create(user=free_user)
        Wallet.objects.create(architect=free, balance=5)
        offer = send_offer(self.order("Nukus"), free, source=O.Source.ARCHITECT_APPLIED)
        accept_offer(offer)
        self.client.force_login(free_user)
        self.assertContains(self.client.get("/freelancer/dashboard/?tab=market"), "Yakunlash")
        self.client.post(f"/ariza/{offer.pk}/arxitektor-yakunlash/")
        self.assertContains(self.client.get("/freelancer/dashboard/?tab=finished"), "Nukus")


class OfferDetailPageTests(TestCase):
    """The "Batafsil" page: full project details; the client's contact only after acceptance;
    visible to the architect/studio and to the worker the job is assigned to (not the old one)."""

    def setUp(self):
        self.client_user = User.objects.create_user(phone="+998901111111", password="x", first_name="Aziz", last_name="Karimov", role=User.Role.USER)
        self.owner = make_studio()
        self.w1 = make_employee(self.owner, "Worker1")
        self.w2 = make_employee(self.owner, "Worker2")
        for w in (self.w1, self.w2):
            w.approval_status = ArchitectProfile.ApprovalStatus.APPROVED
            w.save()
        self.app = Application.objects.create(
            owner=self.client_user, rooms_count=3, location="Toshkent", size_m2=90, object_type="apartment",
            service_type="interior", custom_style="Skandinav", estimate_min=1000, estimate_max=1800, description="Yorug' bo'lsin",
        )
        self.offer = send_offer(self.app, self.owner, source=Offer.Source.ARCHITECT_APPLIED)
        self.url = f"/ariza/{self.offer.pk}/batafsil/"

    def test_details_without_contact_before_acceptance(self):
        self.client.force_login(self.owner.user)
        page = self.client.get(self.url)
        for text in ("Skandinav", "Kvartira", "Interyer dizayni", "$1000", "Yorug"):
            self.assertContains(page, text)
        self.assertNotContains(page, "+998901111111")
        self.assertContains(page, "ariza qabul qilingach")

    def test_contact_and_worker_button_after_assignment_and_the_old_worker_is_locked_out(self):
        accept_offer(self.offer)
        assignment = StudioAssignment.objects.get(offer=self.offer)
        assign_worker(assignment, self.w1, deadline="2030-01-01")
        self.client.force_login(self.owner.user)
        self.assertContains(self.client.get(self.url), "+998901111111")
        self.client.force_login(self.w1.user)
        page = self.client.get(self.url)
        self.assertContains(page, "+998901111111")                     # the worker sees the client's contact...
        self.assertContains(page, "Bajarildi")                          # ...and can mark the job finished
        self.client.post(f"/employee/buyurtmalar/{assignment.pk}/bajarildi/")
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, StudioAssignment.Status.DONE)

    def test_a_reassigned_worker_and_strangers_cannot_open_it(self):
        accept_offer(self.offer)
        assignment = StudioAssignment.objects.get(offer=self.offer)
        assign_worker(assignment, self.w1)
        assign_worker(assignment, self.w2)
        self.client.force_login(self.w1.user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.w2.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_the_orders_table_links_to_it_and_shows_the_client_after_acceptance(self):
        accept_offer(self.offer)
        self.client.force_login(self.owner.user)
        page = self.client.get("/studio/dashboard/?tab=orders")
        self.assertContains(page, self.url)
        self.assertContains(page, "Aziz")
        self.assertContains(page, "+998901111111")

    def test_finished_projects_show_the_details(self):
        accept_offer(self.offer)
        self.client.post  # noqa
        self.client.force_login(self.owner.user)
        self.client.post(f"/ariza/{self.offer.pk}/arxitektor-yakunlash/")
        page = self.client.get("/studio/dashboard/?tab=finished")
        for text in ("Skandinav", "Kvartira", "Interyer dizayni", "$1000", "Batafsil"):
            self.assertContains(page, text)
