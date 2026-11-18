import re
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from poydevor.i18n import catalog_1, catalog_2, catalog_3, catalog_4, catalog_5
from poydevor.i18n.content import translate_user_text
from poydevor.i18n.engine import norm, translate_html, translate_text


class CatalogueTests(SimpleTestCase):
    ENTRIES = [e for m in (catalog_1, catalog_2, catalog_3, catalog_4, catalog_5) for e in m.ENTRIES]

    def test_every_entry_has_both_translations_with_the_same_placeholders(self):
        for uz, ru, en in self.ENTRIES:
            with self.subTest(uz=uz):
                self.assertTrue(ru.strip() and en.strip())
                self.assertEqual(uz.count("{}"), ru.count("{}"), "ru placeholders differ")
                self.assertEqual(uz.count("{}"), en.count("{}"), "en placeholders differ")

    def test_no_translation_is_left_in_uzbek(self):
        uzbek = re.compile(r"\b(uchun|yoki|bilan|kerak|mumkin|hali|ta|ariza|loyiha|buyurtma)\b", re.I)
        for uz, ru, en in self.ENTRIES:
            with self.subTest(uz=uz):
                self.assertFalse(uzbek.search(en), en)


class ChoiceLabelsTests(SimpleTestCase):
    def test_every_status_and_type_label_in_the_models_is_translated(self):
        from django.apps import apps
        missing = []
        for model in apps.get_models():
            if model._meta.app_label in ("admin", "auth", "contenttypes", "sessions"):
                continue
            for field in model._meta.get_fields():
                for _value, label in (getattr(field, "choices", None) or []):
                    for lang in ("ru", "en"):
                        if translate_text(norm(str(label)), lang) is None:
                            missing.append((model.__name__, str(label), lang))
        self.assertEqual(missing, [])


class EngineTests(SimpleTestCase):
    def test_exact_and_pattern_texts(self):
        self.assertEqual(translate_text(norm("Chiqish"), "ru"), "Выйти")
        self.assertEqual(translate_text(norm("Chiqish"), "en"), "Log out")
        self.assertEqual(translate_text(norm("Xush kelibsiz, Aziz."), "ru"), "Добро пожаловать, Aziz.")
        self.assertEqual(translate_text(norm("Mijoz sizga loyiha yubordi: Samarqand. Qabul qilish yoki rad etishingiz mumkin."), "en"),
                         "A client sent you a project: Samarqand. You can accept or decline it.")
        self.assertIsNone(translate_text(norm("Alisher Karimov"), "ru"))             # names are never translated
        self.assertIsNone(translate_text(norm("Chiqish"), "uz"))

    def test_apostrophe_variants_and_entities_match(self):
        self.assertEqual(translate_text(norm("Ko&#x27;rish"), "en"), "View")
        self.assertEqual(translate_text(norm("Ko’rish"), "en"), "View")

    def test_html_text_attributes_scripts_and_untouched_parts(self):
        source = (
            '<html lang="uz"><head><title>Bosh sahifa — Poydevor</title></head><body>'
            '<a href="/x/" title="Orqaga">Chiqish</a><p>Alisher Karimov, +998901234567</p>'
            '<input placeholder="Qidirish"><button onsubmit="return confirm(\'Ishonchingiz komilmi? So\\\'rov rad etiladi.\')">Saqlash</button>'
            "<script>var t = 'Yana qo\\'shish'; var keep = 'btn-clay';</script><style>.Chiqish{}</style></body></html>"
        )
        out = translate_html(source, "ru")
        for expected in ('lang="ru"', "Главная — Poydevor", 'title="Назад"', ">Выйти<", "Alisher Karimov, +998901234567",
                         'placeholder="Поиск"', "Вы уверены? Запрос будет отклонён.", "'Добавить ещё'", "'btn-clay'", ".Chiqish{}"):
            self.assertIn(expected, out)
        self.assertEqual(translate_html(source, "uz"), source)


class LanguageSwitchTests(TestCase):
    def test_switching_sets_a_cookie_and_translates_pages(self):
        page = self.client.get(reverse("accounts:welcome"))
        self.assertContains(page, "Kirish")
        response = self.client.get(reverse("set_language", args=["ru"]), {"next": reverse("accounts:welcome")})
        self.assertEqual(self.client.cookies["lang"].value, "ru")
        russian = self.client.get(reverse("accounts:welcome"))
        self.assertContains(russian, "Войти")
        self.assertContains(russian, 'lang="ru"')
        self.client.get(reverse("set_language", args=["en"]))
        self.assertContains(self.client.get(reverse("accounts:welcome")), "Sign in")
        self.client.get(reverse("set_language", args=["uz"]))
        self.assertContains(self.client.get(reverse("accounts:welcome")), "Kirish")

    def test_unknown_language_and_outside_addresses_are_ignored(self):
        response = self.client.get(reverse("set_language", args=["xx"]), {"next": "https://evil.example/"})
        self.assertNotIn("lang", self.client.cookies)
        self.assertEqual(response["Location"], "/")

    def test_the_switcher_is_in_the_menu_and_marks_the_current_language(self):
        self.client.cookies["lang"] = "ru"
        page = self.client.get(reverse("accounts:welcome"))
        self.assertContains(page, "/til/en/")
        self.assertContains(page, "bg-charcoal-900 text-white\">RU<")

    def test_error_and_form_pages_have_no_uzbek_left(self):
        uzbek = re.compile(r"(o'|g'|oʻ)|\b(uchun|yoki|bilan|kerak|mumkin|hali|yo'q|qil\w+|ko'r\w+|tanla\w+|yubor\w+|saqla\w+|parol\w*|ariza\w*|loyiha\w*)\b", re.I)
        for lang in ("ru", "en"):
            self.client.cookies["lang"] = lang
            for url in (reverse("accounts:welcome"), reverse("accounts:login"), reverse("accounts:signup"),
                        reverse("architects:select_type"), reverse("architects:register_studio"),
                        reverse("architects:register_freelancer"), reverse("architects:register_employee"),
                        reverse("architects:list"), reverse("architects:project_gallery"), "/yoq-sahifa/"):
                with self.subTest(lang=lang, url=url):
                    html = self.client.get(url).content.decode()
                    body = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
                    left = [m.group(0) for m in uzbek.finditer(body)]
                    self.assertEqual(left, [], f"Uzbek left on {url} in {lang}")


class UserContentTranslationTests(TestCase):
    def test_without_a_key_the_original_is_shown(self):
        self.assertEqual(translate_user_text("Zamonaviy", "ru"), "Современный")  # a known fixed text
        self.assertEqual(translate_user_text("Bu mening maxsus tavsifim", "ru"), "Bu mening maxsus tavsifim")
        self.assertEqual(translate_user_text("", "ru"), "")

    @override_settings(GOOGLE_TRANSLATE_API_KEY="test-key")
    def test_a_translation_is_asked_for_once_then_kept(self):
        from translations.models import ContentTranslation
        with mock.patch("poydevor.i18n.content._ask_provider", return_value="Hello") as ask:
            self.assertEqual(translate_user_text("Salom dunyo yangi matn", "en"), "Hello")
            self.assertEqual(translate_user_text("Salom dunyo yangi matn", "en"), "Hello")
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(ContentTranslation.objects.count(), 1)

    def test_a_failing_service_never_breaks_the_page(self):
        with mock.patch("poydevor.i18n.content._ask_provider", return_value=None):
            self.assertEqual(translate_user_text("Boshqa yangi matn", "en"), "Boshqa yangi matn")

    @override_settings(GOOGLE_TRANSLATE_API_KEY="test-key")
    def test_project_text_goes_through_the_service_but_names_do_not(self):
        from accounts.models import User
        from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject
        user = User.objects.create_user(phone="+998901112222", first_name="Nodir", last_name="Karimov", role=User.Role.ARCHITECT)
        profile = ArchitectProfile.objects.create(user=user, portfolio_exempt=True)
        project = PortfolioProject.objects.create(architect=profile, title="Zamonaviy hovli uyi", description="Ikki qavatli uy")
        PortfolioImage.objects.create(project=project, image="portfolio/p.jpg", order=0)
        self.client.cookies["lang"] = "en"
        with mock.patch("poydevor.i18n.content._ask_provider", side_effect=lambda text, lang: f"EN:{text}"):
            page = self.client.get(reverse("architects:project_gallery"))
        self.assertContains(page, "EN:Zamonaviy hovli uyi")
        self.assertContains(page, "EN:Ikki qavatli uy")
        self.assertContains(page, "Nodir Karimov")                  # names stay as they are
        self.assertNotContains(page, "EN:Nodir")
