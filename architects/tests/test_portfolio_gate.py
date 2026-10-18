import itertools

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Style
from architects.services import set_approval
from offers.models import Offer
from offers.services import ArchitectNotAllowedError, send_offer
from wallet.models import Wallet

Kind = ArchitectProfile.Kind
Approval = ArchitectProfile.ApprovalStatus
_phones = itertools.count(1000)


def make_architect(kind=Kind.FREELANCER, status=Approval.APPROVED, exempt=False, name="Nodir"):
    user = User.objects.create_user(
        phone=f"+99890{next(_phones):07d}", first_name=name, last_name="Tester", role=User.Role.ARCHITECT,
    )
    profile = ArchitectProfile.objects.create(user=user, kind=kind, approval_status=status, portfolio_exempt=exempt)
    if status == Approval.APPROVED and kind != Kind.STUDIO_EMPLOYEE:
        Wallet.objects.create(architect=profile, balance=20)
    return profile


def add_project(profile, photos=1, title=None):
    style = Style.objects.get_or_create(name="Zamonaviy")[0]
    number = profile.projects.count() + 1
    project = PortfolioProject.objects.create(
        architect=profile, title=title or f"{profile.user.first_name} loyiha {number}", style=style,
        description="Tavsif", order=number,
    )
    for i in range(photos):
        PortfolioImage.objects.create(project=project, image=f"portfolio/{profile.pk}-{number}-{i}.jpg", order=i)
    return project


def complete_portfolio(profile, projects=None, verified=True):
    for _ in range(projects or profile.portfolio_requirements["projects"]):
        add_project(profile)
    profile.refresh_from_db()
    if verified:
        profile.portfolio_verification = ArchitectProfile.VerificationStatus.VERIFIED
        profile.save(update_fields=["portfolio_verification"])
    return profile


class PortfolioRuleTests(TestCase):
    def test_freelancer_needs_5_projects_each_with_a_photo(self):
        profile = make_architect()
        self.assertEqual(profile.portfolio_requirements, {"projects": 5, "images": 1})
        for _ in range(4):
            add_project(profile)
        profile.refresh_from_db()
        self.assertFalse(profile.portfolio_complete)
        add_project(profile)
        profile.refresh_from_db()
        self.assertTrue(profile.portfolio_complete)

    def test_studio_needs_10_projects_each_with_a_photo(self):
        profile = make_architect(Kind.STUDIO_OWNER)
        self.assertEqual(profile.portfolio_requirements, {"projects": 10, "images": 1})
        for _ in range(9):
            add_project(profile)
        profile.refresh_from_db()
        self.assertFalse(profile.portfolio_complete)
        add_project(profile)
        profile.refresh_from_db()
        self.assertTrue(profile.portfolio_complete)

    def test_a_project_without_a_photo_does_not_count(self):
        profile = make_architect()
        for _ in range(4):
            add_project(profile)
        add_project(profile, photos=0)
        profile.refresh_from_db()
        self.assertFalse(profile.portfolio_complete)
        progress = profile.portfolio_progress()
        self.assertEqual((progress["ready"], progress["total"], progress["missing"]), (4, 5, 1))

    def test_more_photos_than_the_minimum_are_fine(self):
        profile = make_architect()
        for _ in range(5):
            add_project(profile, photos=4)
        profile.refresh_from_db()
        self.assertTrue(profile.portfolio_complete)

    def test_status_follows_photos_being_added_and_removed(self):
        profile = complete_portfolio(make_architect())
        self.assertTrue(profile.portfolio_complete)
        PortfolioImage.objects.filter(project=profile.projects.first()).first().delete()   # first project loses its only photo
        profile.refresh_from_db()
        self.assertFalse(profile.portfolio_complete)
        PortfolioImage.objects.create(project=profile.projects.first(), image="portfolio/back.jpg")
        profile.refresh_from_db()
        self.assertTrue(profile.portfolio_complete)
        profile.projects.first().delete()                                                    # 5 -> 4 projects
        profile.refresh_from_db()
        self.assertFalse(profile.portfolio_complete)

    def test_employees_keep_no_portfolio(self):
        employee = make_architect(Kind.STUDIO_EMPLOYEE)
        self.assertIsNone(employee.portfolio_requirements)
        self.assertFalse(employee.can_take_offers)

    def test_profiles_created_by_hand_are_excused_by_default(self):
        user = User.objects.create_user(phone="+998909998877", first_name="H", last_name="H", role=User.Role.ARCHITECT)
        self.assertTrue(ArchitectProfile.objects.create(user=user).portfolio_exempt)


class HiddenUntilCompleteTests(TestCase):
    def setUp(self):
        self.incomplete = make_architect(name="Yarim")
        add_project(self.incomplete, title="Yashirin loyiha")
        self.complete = complete_portfolio(make_architect(name="Tayyor"))
        self.excused = make_architect(exempt=True, name="Ozod")
        add_project(self.excused, photos=1, title="Ozod loyiha")

    def test_architect_list_only_shows_complete_or_excused_architects(self):
        page = self.client.get(reverse("architects:list"))
        self.assertContains(page, "Tayyor")
        self.assertContains(page, "Ozod")
        self.assertNotContains(page, "Yarim")

    def test_incomplete_profile_page_does_not_exist_for_others(self):
        self.assertEqual(self.client.get(reverse("architects:detail", args=[self.incomplete.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("architects:detail", args=[self.complete.pk])).status_code, 200)

    def test_projects_of_an_incomplete_architect_are_hidden_everywhere(self):
        gallery = self.client.get(reverse("architects:project_gallery"))
        self.assertNotContains(gallery, "Yashirin loyiha")
        self.assertContains(gallery, "Tayyor loyiha 1")
        self.assertContains(gallery, "Ozod loyiha")   # an excused architect's projects still show

    def test_a_project_without_a_photo_stays_hidden_even_for_a_complete_architect(self):
        add_project(self.complete, photos=0, title="Rasmsiz loyiha")
        self.assertNotContains(self.client.get(reverse("architects:project_gallery")), "Rasmsiz loyiha")
        self.assertNotContains(self.client.get(reverse("architects:detail", args=[self.complete.pk])), "Rasmsiz loyiha")

    def test_they_appear_the_moment_the_portfolio_is_finished_and_verified(self):
        for _ in range(4):
            add_project(self.incomplete)
        self.incomplete.refresh_from_db()
        self.assertTrue(self.incomplete.portfolio_complete)
        # Finished but not yet looked at by an admin: still hidden.
        self.assertNotContains(self.client.get(reverse("architects:list")), "Yarim")
        self.incomplete.portfolio_verification = ArchitectProfile.VerificationStatus.VERIFIED
        self.incomplete.save(update_fields=["portfolio_verification"])
        self.assertContains(self.client.get(reverse("architects:list")), "Yarim")
        self.assertContains(self.client.get(reverse("architects:project_gallery")), "Yashirin loyiha")

    def test_an_incomplete_architect_cannot_be_invited(self):
        client_user = User.objects.create_user(phone="+998907776655", first_name="C", last_name="D", role=User.Role.USER)
        Application.objects.create(owner=client_user, rooms_count=2, location="Toshkent")
        self.client.force_login(client_user)
        self.assertEqual(self.client.get(reverse("offers:send", args=[self.incomplete.pk])).status_code, 404)


class CannotOrderUntilCompleteTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(phone="+998907776655", first_name="Aziz", last_name="K", role=User.Role.USER)
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        self.architect = make_architect()
        self.url = reverse("offers:architect_apply", args=[self.application.pk])
        self.client.force_login(self.architect.user)

    def balance(self):
        return Wallet.objects.get(architect=self.architect).balance

    def test_applying_is_refused_with_a_pointer_to_the_portfolio(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, "/freelancer/dashboard/?tab=room", fetch_redirect_response=False)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Offer.objects.exists())
        self.assertEqual(self.balance(), 20)
        followed = self.client.get(response.url)
        self.assertContains(followed, "Portfolio to&#x27;ldirilmaguncha")

    def test_the_service_refuses_too(self):
        with self.assertRaises(ArchitectNotAllowedError):
            send_offer(self.application, self.architect, source=Offer.Source.ARCHITECT_APPLIED)

    def test_accepting_an_invitation_is_refused(self):
        offer = Offer.objects.create(application=self.application, architect=self.architect, source=Offer.Source.USER_INVITED)
        response = self.client.post(reverse("offers:respond", args=[offer.pk]), {"decision": "accept"})
        self.assertRedirects(response, "/freelancer/dashboard/?tab=room", fetch_redirect_response=False)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.PENDING)
        self.assertEqual(self.application.offers.filter(status=Offer.Status.ACCEPTED).count(), 0)

    def test_declining_an_invitation_is_still_possible(self):
        offer = Offer.objects.create(application=self.application, architect=self.architect, source=Offer.Source.USER_INVITED)
        self.client.post(reverse("offers:respond", args=[offer.pk]), {"decision": "reject"})
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.REJECTED)

    def test_market_tab_is_locked(self):
        page = self.client.get("/freelancer/dashboard/?tab=market")
        self.assertContains(page, "portfolio to'ldirilgach ochiladi")
        self.assertEqual(list(page.context["open_applications"]), [])
        self.assertNotContains(page, self.url)

    def test_everything_works_once_the_portfolio_is_complete(self):
        complete_portfolio(self.architect)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(self.url)
        self.assertTrue(Offer.objects.filter(architect=self.architect).exists())
        self.assertEqual(self.balance(), 10)

    def test_a_finished_but_unverified_portfolio_still_cannot_apply(self):
        complete_portfolio(self.architect, verified=False)
        self.architect.refresh_from_db()
        self.assertEqual(self.architect.portfolio_verification, ArchitectProfile.VerificationStatus.PENDING)
        self.assertFalse(self.architect.can_take_offers)

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Offer.objects.exists())
        followed = self.client.get(response.url)
        self.assertContains(followed, "48 soat")

        room = self.client.get("/freelancer/dashboard/?tab=room")
        self.assertContains(room, "48 soat")

    def test_works_again_once_admin_verifies_it(self):
        complete_portfolio(self.architect, verified=False)
        self.architect.portfolio_verification = ArchitectProfile.VerificationStatus.VERIFIED
        self.architect.save(update_fields=["portfolio_verification"])
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_excused_architects_are_not_blocked(self):
        self.architect.portfolio_exempt = True
        self.architect.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)


class WorkspaceDemandsPortfolioTests(TestCase):
    def test_incomplete_architect_lands_on_the_portfolio_and_sees_a_demand(self):
        profile = make_architect()
        self.client.force_login(profile.user)
        page = self.client.get("/freelancer/dashboard/")
        self.assertEqual(page.context["tab"], "room")
        self.assertContains(page, "Portfolioni to'ldiring")
        self.assertContains(page, "0 / 5 loyiha tayyor")
        self.assertContains(page, "hech kimga ko'rinmaydi")
        # other tabs carry a reminder that links back to it
        self.assertContains(self.client.get("/freelancer/dashboard/?tab=store"), "Portfolio to'ldirilmagan")

    def test_studio_owner_is_asked_for_10_projects(self):
        profile = make_architect(Kind.STUDIO_OWNER)
        from architects.models import Studio
        Studio.objects.create(
            owner=profile, name="ArcDes", founded_on="2020-05-15", founders="A", responsible_person="A",
            responsible_birth_date="1992-08-12", email="a@a.uz", phone="+998901234567", staff_count=3, projects_count=4,
        )
        self.client.force_login(profile.user)
        page = self.client.get("/studio/dashboard/")
        self.assertEqual(page.context["tab"], "room")
        self.assertContains(page, "0 / 10 loyiha tayyor")

    def test_progress_and_projects_without_a_photo_are_shown(self):
        profile = make_architect()
        add_project(profile, photos=1)
        add_project(profile, photos=0, title="Rasmsiz uy")
        self.client.force_login(profile.user)
        page = self.client.get("/freelancer/dashboard/?tab=room")
        self.assertContains(page, "1 / 5 loyiha tayyor")
        self.assertContains(page, "Rasm yo'q — kamida bitta rasm qo'shing")
        self.assertContains(page, reverse("architects:my_project", args=[profile.projects.first().pk]))   # cards open the owner's page
        self.assertNotContains(page, "asosiy")                            # no favourite-photo talk

    def test_complete_portfolio_shows_the_normal_dashboard_again(self):
        profile = complete_portfolio(make_architect())
        self.client.force_login(profile.user)
        page = self.client.get("/freelancer/dashboard/")
        self.assertEqual(page.context["tab"], "market")
        self.assertNotContains(page, "hech kimga ko'rinmaydi")
        room = self.client.get("/freelancer/dashboard/?tab=room")
        self.assertNotContains(room, "Portfolioni to'ldiring")   # the demand disappears once it is done
        self.assertNotContains(room, "Portfolio to'liq")         # ...and is not replaced by another notice


class PendingApplicantBuildsPortfolioTests(TestCase):
    """Right after signing up (before approval) the person can already start."""

    def setUp(self):
        self.profile = make_architect(status=Approval.PENDING)
        self.client.force_login(self.profile.user)

    def test_status_page_for_a_pending_account_makes_no_promises_about_review_times(self):
        page = self.client.get(reverse("architects:register_status"))
        self.assertContains(page, "ko'rib chiqilmoqda")
        self.assertNotContains(page, "48 soat")

    def test_portfolio_page_works_while_pending(self):
        page = self.client.get(reverse("architects:portfolio"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Portfolioni to'ldiring")

    def test_a_project_is_created_in_one_step_and_lands_back_on_the_portfolio(self):
        import shutil, tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        media = tempfile.mkdtemp(prefix="poydevor-test-media-")
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        gif = (b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04"
               b"\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b")
        style = Style.objects.create(name="Loft")
        url = reverse("architects:project_create")
        bad = self.client.post(url, {"title": "", "style": ""})
        self.assertEqual(set(bad.context["form"].errors), {"title", "style", "images", "attachment"})
        with override_settings(MEDIA_ROOT=media):
            good = self.client.post(url, {
                "title": "Loft uy", "style": style.pk,                     # no description
                "attachment": SimpleUploadedFile("reja.pdf", b"%PDF-1.4", content_type="application/pdf"),
                "images": [SimpleUploadedFile("a.gif", gif, content_type="image/gif")],
            })
        self.assertRedirects(good, reverse("architects:portfolio"), fetch_redirect_response=False)
        project = PortfolioProject.objects.get(title="Loft uy")
        self.assertEqual((project.style, project.description, project.images.count()), (style, "", 1))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.portfolio_progress()["ready"], 1)

    def test_the_form_marks_only_the_required_fields(self):
        html = self.client.get(reverse("architects:project_create")).content.decode()
        self.assertIn("Loyiha tavsifi (ixtiyoriy)", html)
        self.assertEqual(html.count('<span class="text-clay-600">*</span>'), 4)   # title, type, photos, file

    def test_pending_applicant_still_cannot_use_the_dashboard(self):
        response = self.client.get("/freelancer/dashboard/")
        self.assertRedirects(response, reverse("architects:register_status"), fetch_redirect_response=False)

    def test_approval_sends_them_to_the_portfolio_first(self):
        set_approval(self.profile, Approval.APPROVED)
        self.client.force_login(self.profile.user)
        self.assertEqual(self.client.get("/freelancer/dashboard/").context["tab"], "room")
        self.assertEqual(self.client.get(reverse("architects:portfolio")).status_code, 302)   # now lives in the tab

    def test_rejected_applicants_and_employees_have_no_portfolio_pages(self):
        rejected = make_architect(status=Approval.REJECTED)
        self.client.force_login(rejected.user)
        self.assertRedirects(self.client.get(reverse("architects:portfolio")), reverse("architects:register_status"), fetch_redirect_response=False)
        employee = make_architect(Kind.STUDIO_EMPLOYEE)
        self.client.force_login(employee.user)
        self.assertEqual(self.client.get(reverse("architects:project_create")).status_code, 302)
