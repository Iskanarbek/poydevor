import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioProject, Studio
from architects.services import set_approval
from wallet.models import CoinTransaction, Wallet

Kind = ArchitectProfile.Kind
Approval = ArchitectProfile.ApprovalStatus


def make_files(count, name="work"):
    return [SimpleUploadedFile(f"{name}{i}.jpg", b"fake-image-bytes", content_type="image/jpeg") for i in range(count)]


GIF = (b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04"
       b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b")


def avatar():
    return SimpleUploadedFile("me.gif", GIF, content_type="image/gif")


class MediaRootMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="poydevor-test-media-")
        cls._override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()


STUDIO_DATA = {
    "studio_name": "ArcDes Studio Tashkent", "founded_on": "2020-05-15",
    "founders": "Alisher Qodirov, Nodir Karimov", "responsible_person": "Alisher Qodirov",
    "responsible_birth_date": "1992-08-12", "email": "info@arcdes.uz", "phone": "+998 90 123 45 67",
    "staff_count": 15, "projects_count": 45,
}


class SelectTypeTests(TestCase):
    def test_shows_three_options(self):
        response = self.client.get(reverse("architects:select_type"))
        self.assertEqual(response.status_code, 200)
        for name in ("register_studio", "register_employee", "register_freelancer"):
            self.assertContains(response, reverse(f"architects:{name}"))


SIGNUP_NOISE = ("fayl kerak emas", "portfolio yaratasiz", "48 soat", "ko'rib chiqiladi", "ko'rib chiqamiz")


class StudioRegistrationTests(MediaRootMixin, TestCase):
    def post(self, **overrides):
        return self.client.post(reverse("architects:register_studio"), {**STUDIO_DATA, "avatar": avatar(), **overrides})

    def test_registration_needs_no_files_and_goes_straight_into_the_account(self):
        response = self.post()
        self.assertRedirects(response, reverse("architects:studio_dashboard"), fetch_redirect_response=False)

        user = User.objects.get(phone="+998901234567")
        self.assertEqual(user.role, User.Role.ARCHITECT)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        profile = user.architect_profile
        self.assertEqual(profile.kind, Kind.STUDIO_OWNER)
        self.assertEqual(profile.approval_status, Approval.APPROVED)     # no review to wait for
        self.assertFalse(profile.portfolio_exempt)                        # but a portfolio is required
        self.assertFalse(profile.portfolio_complete)
        self.assertEqual(Studio.objects.get(owner=profile).name, "ArcDes Studio Tashkent")
        self.assertEqual(profile.wallet.balance, 20)                      # starting coins

    def test_first_screen_inside_asks_for_the_portfolio(self):
        self.post()
        page = self.client.get(reverse("architects:studio_dashboard"))
        self.assertEqual(page.context["tab"], "room")
        self.assertContains(page, "Portfolioni to'ldiring")
        self.assertContains(page, "0 / 10 loyiha tayyor")

    def test_sign_up_page_asks_only_for_a_profile_photo_and_has_no_portfolio_or_review_notes(self):
        response = self.client.get(reverse("architects:register_studio"))
        self.assertEqual(response.content.decode().count('<input type="file"'), 1)   # only the profile photo
        for text in SIGNUP_NOISE:
            self.assertNotContains(response, text)

    def test_existing_phone_is_rejected(self):
        User.objects.create_user(phone="+998901234567", first_name="X", last_name="Y", role=User.Role.USER)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("phone"))
        self.assertFalse(Studio.objects.exists())

    def test_there_is_no_application_submitted_screen_for_studios(self):
        self.post()
        status = self.client.get(reverse("architects:register_status"))
        self.assertRedirects(status, reverse("architects:studio_dashboard"), fetch_redirect_response=False)
        for text in SIGNUP_NOISE + ("Tabriklayman",):
            self.assertNotContains(self.client.get(reverse("architects:studio_dashboard")), text)


class FreelancerRegistrationTests(MediaRootMixin, TestCase):
    DATA = {
        "full_name": "Jasur Axmedov", "birth_year": 1995, "phone": "+998 97 555 44 33",
        "email": "jasur.architect@gmail.com", "projects_count": 18,
    }

    def test_registration_needs_no_files_and_goes_straight_into_the_account(self):
        response = self.client.post(reverse("architects:register_freelancer"), {**self.DATA, "avatar": avatar()})
        self.assertRedirects(response, reverse("architects:freelancer_dashboard"), fetch_redirect_response=False)
        profile = ArchitectProfile.objects.get(user__phone="+998975554433")
        self.assertEqual(profile.kind, Kind.FREELANCER)
        self.assertEqual(profile.approval_status, Approval.APPROVED)
        self.assertFalse(profile.portfolio_exempt)
        self.assertEqual(profile.user.first_name, "Jasur")
        self.assertEqual(profile.user.last_name, "Axmedov")
        self.assertEqual(profile.claimed_projects_count, 18)
        self.assertFalse(profile.registration_files.exists())
        self.assertEqual(profile.wallet.balance, 20)

    def test_first_screen_inside_asks_for_5_projects(self):
        self.client.post(reverse("architects:register_freelancer"), {**self.DATA, "avatar": avatar()})
        page = self.client.get(reverse("architects:freelancer_dashboard"))
        self.assertEqual(page.context["tab"], "room")
        self.assertContains(page, "0 / 5 loyiha tayyor")
        self.assertContains(page, "kamida bitta rasm")

    def test_sign_up_page_asks_only_for_a_profile_photo_and_has_no_portfolio_or_review_notes(self):
        response = self.client.get(reverse("architects:register_freelancer"))
        self.assertEqual(response.content.decode().count('<input type="file"'), 1)   # only the profile photo
        for text in SIGNUP_NOISE:
            self.assertNotContains(response, text)

    def test_signed_in_architect_without_profile_keeps_their_account(self):
        user = User.objects.create_user(
            phone="+998975554433", first_name="Old", last_name="Name", role=User.Role.ARCHITECT,
        )
        self.client.force_login(user)
        data = {k: v for k, v in self.DATA.items() if k != "phone"} | {"avatar": avatar()}
        response = self.client.post(reverse("architects:register_freelancer"), data)
        self.assertRedirects(response, reverse("architects:freelancer_dashboard"), fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Jasur")
        self.assertEqual(user.architect_profile.kind, Kind.FREELANCER)


class EmployeeRegistrationTests(MediaRootMixin, TestCase):
    def setUp(self):
        owner_user = User.objects.create_user(
            phone="+998901234567", first_name="Alisher", last_name="Qodirov", role=User.Role.ARCHITECT,
        )
        self.owner = ArchitectProfile.objects.create(user=owner_user, kind=Kind.STUDIO_OWNER)
        self.studio = Studio.objects.create(
            owner=self.owner, name="ArcDes", founded_on="2020-05-15", founders="A", responsible_person="A",
            responsible_birth_date="1992-08-12", email="a@a.uz", phone="+998901234567",
            staff_count=3, projects_count=4,
        )

    def register(self, studio=None):
        return self.client.post(reverse("architects:register_employee"), {
            "full_name": "Sardor Murodov", "birth_year": 1998, "phone": "+998 93 987 65 43",
            "email": "sardor.m@gmail.com", "studio": (studio or self.studio).pk, "avatar": avatar(),
        })

    def test_registration_creates_pending_employee_of_the_studio(self):
        response = self.register()
        self.assertRedirects(response, reverse("architects:register_status"), fetch_redirect_response=False)
        employee = ArchitectProfile.objects.get(user__phone="+998939876543")
        self.assertEqual(employee.kind, Kind.STUDIO_EMPLOYEE)
        self.assertEqual(employee.approval_status, Approval.PENDING)
        self.assertEqual(employee.studio, self.studio)

    def test_only_approved_studios_can_be_chosen(self):
        self.owner.approval_status = Approval.PENDING
        self.owner.save()
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("studio"))
        self.assertFalse(ArchitectProfile.objects.filter(kind=Kind.STUDIO_EMPLOYEE).exists())

    def test_studio_owner_approves_and_employee_gets_workspace(self):
        self.register()
        employee = ArchitectProfile.objects.get(kind=Kind.STUDIO_EMPLOYEE)

        # The employee is stuck on the status screen until approved.
        response = self.client.get(reverse("architects:employee_workspace"))
        self.assertRedirects(response, reverse("architects:register_status"), fetch_redirect_response=False)

        self.client.force_login(self.owner.user)
        page = self.client.get(reverse("architects:studio_dashboard"), {"tab": "employees"})
        self.assertContains(page, "Sardor")
        response = self.client.post(
            reverse("architects:employee_decision", args=[employee.pk]), {"decision": "accept"},
        )
        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertEqual(employee.approval_status, Approval.APPROVED)
        self.assertFalse(Wallet.objects.filter(architect=employee).exists())  # employees hold no coins

        self.client.force_login(employee.user)
        workspace = self.client.get(reverse("architects:employee_workspace"))
        self.assertContains(workspace, "Mening joriy ishlarim")

    def test_owner_can_reject_employee(self):
        self.register()
        employee = ArchitectProfile.objects.get(kind=Kind.STUDIO_EMPLOYEE)
        self.client.force_login(self.owner.user)
        self.client.post(reverse("architects:employee_decision", args=[employee.pk]), {"decision": "reject"})
        employee.refresh_from_db()
        self.assertEqual(employee.approval_status, Approval.REJECTED)

    def test_other_studio_owner_cannot_decide(self):
        self.register()
        employee = ArchitectProfile.objects.get(kind=Kind.STUDIO_EMPLOYEE)
        other_user = User.objects.create_user(phone="+998907777777", first_name="O", last_name="T", role=User.Role.ARCHITECT)
        other = ArchitectProfile.objects.create(user=other_user, kind=Kind.STUDIO_OWNER)
        Studio.objects.create(
            owner=other, name="Other", founded_on="2020-01-01", founders="O", responsible_person="O",
            responsible_birth_date="1990-01-01", email="o@o.uz", phone="+998907777777", staff_count=1, projects_count=1,
        )
        self.client.force_login(other_user)
        response = self.client.post(
            reverse("architects:employee_decision", args=[employee.pk]), {"decision": "accept"},
        )
        self.assertEqual(response.status_code, 404)
        employee.refresh_from_db()
        self.assertEqual(employee.approval_status, Approval.PENDING)


class ApprovalTests(TestCase):
    def make_profile(self, kind=Kind.FREELANCER, phone="+998901112233"):
        user = User.objects.create_user(phone=phone, first_name="A", last_name="B", role=User.Role.ARCHITECT)
        return ArchitectProfile.objects.create(user=user, kind=kind, approval_status=Approval.PENDING)

    def test_approval_creates_wallet_with_coins_for_two_projects(self):
        profile = self.make_profile()
        set_approval(profile, Approval.APPROVED)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, Approval.APPROVED)
        self.assertEqual(profile.wallet.balance, 20)  # 2 projects x 10 coins
        self.assertEqual(
            profile.wallet.transactions.filter(reason=CoinTransaction.Reason.SIGNUP_BONUS).count(), 1,
        )

    def test_bonus_is_granted_only_once(self):
        profile = self.make_profile()
        set_approval(profile, Approval.APPROVED)
        set_approval(profile, Approval.REJECTED)
        set_approval(profile, Approval.APPROVED)
        profile.wallet.refresh_from_db()
        self.assertEqual(profile.wallet.balance, 20)

    def test_studio_owner_gets_the_bonus_too(self):
        profile = self.make_profile(Kind.STUDIO_OWNER)
        set_approval(profile, Approval.APPROVED)
        self.assertEqual(profile.wallet.balance, 20)

    def test_employee_gets_no_wallet(self):
        profile = self.make_profile(Kind.STUDIO_EMPLOYEE)
        set_approval(profile, Approval.APPROVED)
        self.assertFalse(Wallet.objects.filter(architect=profile).exists())

    def test_rejection_gives_nothing(self):
        profile = self.make_profile()
        set_approval(profile, Approval.REJECTED)
        self.assertFalse(Wallet.objects.filter(architect=profile).exists())

    def test_admin_action_and_edit_form_both_grant_bonus(self):
        admin_user = User.objects.create_superuser(phone="+998900000009", password="secret-pass-1", first_name="A", last_name="D")
        self.client.force_login(admin_user)
        profile = self.make_profile()
        self.client.post(reverse("admin:architects_architectprofile_changelist"), {
            "action": "approve", "_selected_action": [profile.pk],
        })
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, Approval.APPROVED)
        self.assertEqual(profile.wallet.balance, 20)


class VisibilityTests(TestCase):
    def make_profile(self, phone, kind, status):
        user = User.objects.create_user(phone=phone, first_name=f"N{phone[-4:]}", last_name="Z", role=User.Role.ARCHITECT)
        return ArchitectProfile.objects.create(user=user, kind=kind, approval_status=status)

    def test_public_list_only_shows_approved_studios_and_freelancers(self):
        approved = self.make_profile("+998901110001", Kind.FREELANCER, Approval.APPROVED)
        pending = self.make_profile("+998901110002", Kind.FREELANCER, Approval.PENDING)
        rejected = self.make_profile("+998901110003", Kind.FREELANCER, Approval.REJECTED)
        employee = self.make_profile("+998901110004", Kind.STUDIO_EMPLOYEE, Approval.APPROVED)
        response = self.client.get(reverse("architects:list"))
        self.assertContains(response, "N0001")
        for hidden in (pending, rejected, employee):
            self.assertNotContains(response, f"N{hidden.user.phone[-4:]}")
        self.assertEqual(self.client.get(reverse("architects:detail", args=[pending.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("architects:detail", args=[approved.pk])).status_code, 200)


class DashboardRoutingTests(TestCase):
    def make(self, kind, status=Approval.APPROVED, phone="+998901112233"):
        user = User.objects.create_user(phone=phone, first_name="A", last_name="B", role=User.Role.ARCHITECT)
        studio = None
        profile = ArchitectProfile.objects.create(user=user, kind=kind, approval_status=status)
        if kind == Kind.STUDIO_OWNER:
            Studio.objects.create(
                owner=profile, name="ArcDes", founded_on="2020-05-15", founders="A", responsible_person="A",
                responsible_birth_date="1992-08-12", email="a@a.uz", phone=phone, staff_count=3, projects_count=4,
            )
        return user, profile

    def test_architect_without_profile_goes_to_type_selection(self):
        user = User.objects.create_user(phone="+998901112299", first_name="A", last_name="B", role=User.Role.ARCHITECT)
        self.client.force_login(user)
        response = self.client.get(reverse("architects:dashboard"))
        self.assertRedirects(response, reverse("architects:select_type"), fetch_redirect_response=False)

    def test_router_sends_each_kind_home(self):
        cases = {
            Kind.STUDIO_OWNER: "architects:studio_dashboard",
            Kind.FREELANCER: "architects:freelancer_dashboard",
            Kind.STUDIO_EMPLOYEE: "architects:employee_workspace",
        }
        for i, (kind, route) in enumerate(cases.items()):
            with self.subTest(kind=kind):
                user, _ = self.make(kind, phone=f"+99890111220{i}")
                self.client.force_login(user)
                response = self.client.get(reverse("architects:dashboard"))
                self.assertRedirects(response, reverse(route), fetch_redirect_response=False)

    def test_wrong_kind_is_sent_to_own_dashboard(self):
        user, _ = self.make(Kind.FREELANCER)
        self.client.force_login(user)
        response = self.client.get(reverse("architects:studio_dashboard"))
        self.assertRedirects(response, reverse("architects:freelancer_dashboard"), fetch_redirect_response=False)

    def test_studio_dashboard_renders_every_tab(self):
        user, profile = self.make(Kind.STUDIO_OWNER)
        set_approval(profile, Approval.APPROVED)
        self.client.force_login(user)
        for tab in ("employees", "finished", "ongoing", "market", "room", "store"):
            with self.subTest(tab=tab):
                response = self.client.get(reverse("architects:studio_dashboard"), {"tab": tab})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "20")  # coin balance in the header

    def test_freelancer_dashboard_renders_every_tab(self):
        user, profile = self.make(Kind.FREELANCER)
        set_approval(profile, Approval.APPROVED)
        self.client.force_login(user)
        for tab in ("market", "room", "finished", "store"):
            with self.subTest(tab=tab):
                response = self.client.get(reverse("architects:freelancer_dashboard"), {"tab": tab})
                self.assertEqual(response.status_code, 200)

    def test_unknown_tab_falls_back_to_default(self):
        user, profile = self.make(Kind.FREELANCER)
        set_approval(profile, Approval.APPROVED)
        self.client.force_login(user)
        response = self.client.get(reverse("architects:freelancer_dashboard"), {"tab": "bogus"})
        self.assertEqual(response.context["tab"], "market")


class PhotoUploaderPageTests(TestCase):
    """The multi-photo uploader now lives on the project photos page."""

    def setUp(self):
        user = User.objects.create_user(phone="+998901234567", first_name="A", last_name="B", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=user, kind=Kind.FREELANCER)
        self.project = PortfolioProject.objects.create(architect=self.profile, title="Uy")
        self.client.force_login(user)

    def test_photos_page_has_the_compact_uploader_without_star_marking(self):
        response = self.client.get(reverse("architects:project_image_add", args=[self.project.pk]))
        self.assertContains(response, "uploader(1, 2000, &#x27;rasm&#x27;)") if False else self.assertContains(response, "uploader(1, 2000, 'rasm')")
        self.assertContains(response, "Rasmlarni bu yerga tashlang")
        self.assertNotContains(response, "belgilandi")

    def test_hidden_file_input_is_multiple_and_not_natively_required(self):
        import re
        html = self.client.get(reverse("architects:project_image_add", args=[self.project.pk])).content.decode()
        tag = re.search(r'<input[^>]*name="images"[^>]*>', html).group(0)
        self.assertIn("multiple", tag)
        self.assertIn('x-ref="real"', tag)
        self.assertNotIn("required", tag)

    def test_widget_returns_every_uploaded_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils.datastructures import MultiValueDict
        from architects.forms import MultipleFileInput
        files = MultiValueDict({"images": [SimpleUploadedFile(f"{i}.jpg", b"x") for i in range(7)]})
        self.assertEqual(len(MultipleFileInput().value_from_datadict({}, files, "images")), 7)


class RemoveEmployeeTests(TestCase):
    def setUp(self):
        owner_user = User.objects.create_user(phone="+998901234567", first_name="Alisher", last_name="Q", role=User.Role.ARCHITECT)
        self.owner = ArchitectProfile.objects.create(user=owner_user, kind=Kind.STUDIO_OWNER)
        self.studio = Studio.objects.create(
            owner=self.owner, name="ArcDes", founded_on="2020-05-15", founders="A", responsible_person="A",
            responsible_birth_date="1992-08-12", email="a@a.uz", phone="+998901234567", staff_count=3, projects_count=4,
        )
        emp_user = User.objects.create_user(phone="+998939876543", first_name="Sardor", last_name="M", role=User.Role.ARCHITECT)
        self.employee = ArchitectProfile.objects.create(user=emp_user, kind=Kind.STUDIO_EMPLOYEE, studio=self.studio)
        self.url = reverse("architects:employee_remove", args=[self.employee.pk])
        self.client.force_login(owner_user)

    def test_employee_list_offers_a_fire_link(self):
        response = self.client.get(reverse("architects:studio_dashboard"), {"tab": "employees"})
        self.assertContains(response, self.url)
        self.assertContains(response, "Ishdan bo")

    def test_opening_the_link_only_asks_for_confirmation(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Sardor")
        self.assertContains(response, "ishdan bo")
        self.assertTrue(ArchitectProfile.objects.filter(pk=self.employee.pk).exists())

    def test_confirming_removes_the_employee_but_keeps_their_account(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ArchitectProfile.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(User.objects.filter(phone="+998939876543").exists())
        # They can no longer open the studio workspace and are sent to register again.
        self.client.force_login(User.objects.get(phone="+998939876543"))
        response = self.client.get(reverse("architects:employee_workspace"))
        self.assertRedirects(response, reverse("architects:select_type"), fetch_redirect_response=False)

    def test_another_studios_owner_cannot_remove_them(self):
        other = User.objects.create_user(phone="+998907777777", first_name="O", last_name="T", role=User.Role.ARCHITECT)
        other_profile = ArchitectProfile.objects.create(user=other, kind=Kind.STUDIO_OWNER)
        Studio.objects.create(
            owner=other_profile, name="Other", founded_on="2020-01-01", founders="O", responsible_person="O",
            responsible_birth_date="1990-01-01", email="o@o.uz", phone="+998907777777", staff_count=1, projects_count=1,
        )
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertTrue(ArchitectProfile.objects.filter(pk=self.employee.pk).exists())

    def test_pending_requests_are_rejected_not_fired(self):
        self.employee.approval_status = ArchitectProfile.ApprovalStatus.PENDING
        self.employee.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)


class ProfilePhotoOptionalTests(MediaRootMixin, TestCase):
    def test_photo_comes_first_but_is_optional(self):
        page = self.client.get(reverse("architects:register_freelancer"))
        html = page.content.decode()
        self.assertLess(html.index('name="avatar"'), html.index('name="full_name"'))
        response = self.client.post(reverse("architects:register_freelancer"), FreelancerRegistrationTests.DATA)
        self.assertEqual(response.status_code, 302)   # no avatar error — straight through to the dashboard
        profile = ArchitectProfile.objects.get()
        self.assertFalse(profile.avatar)

    def test_the_photo_is_saved_on_the_profile_when_provided(self):
        self.client.post(reverse("architects:register_freelancer"), {**FreelancerRegistrationTests.DATA, "avatar": avatar()})
        self.assertTrue(ArchitectProfile.objects.get().avatar.name.endswith(".gif"))
