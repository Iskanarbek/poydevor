# Poydevor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Poydevor, a Django marketplace connecting homeowners with architects, per the approved spec at `docs/superpowers/specs/2026-08-04-poydevor-design.md`.

**Architecture:** Single Django 5 project (`poydevor`) with apps `accounts`, `architects`, `applications`, `offers`, `wallet`, `reviews`. Server-rendered templates (Tailwind CSS + Alpine.js via CDN — no Node build step), SQLite dev DB, local `/media` storage. All UI text in Uzbek.

**Tech Stack:** Django 5, Python 3.11+, SQLite, Tailwind CSS (CDN), Alpine.js (CDN), Pillow (image uploads), Django's built-in test runner (`manage.py test`).

---

## Chunk 1: Project scaffolding & accounts app

**Files:**
- Create: `manage.py`, `poydevor/settings.py`, `poydevor/urls.py`, `poydevor/wsgi.py`, `poydevor/asgi.py`
- Create: `accounts/models.py`, `accounts/managers.py`, `accounts/forms.py`, `accounts/views.py`, `accounts/urls.py`, `accounts/admin.py`
- Create: `templates/base.html`, `templates/accounts/signup.html`, `templates/accounts/login.html`
- Test: `accounts/tests/test_models.py`, `accounts/tests/test_views.py`
- Create: `requirements.txt`

- [ ] **Step 1: Create virtualenv and install Django**

```bash
cd "/Users/iskandarodilov/Desktop/Poydevor"
python3 -m venv venv
source venv/bin/activate
pip install django==5.1 pillow
pip freeze > requirements.txt
```

- [ ] **Step 2: Start the Django project and accounts app**

```bash
django-admin startproject poydevor .
python manage.py startapp accounts
```

- [ ] **Step 3: Configure settings**

Edit `poydevor/settings.py`:
- Add `'accounts'` to `INSTALLED_APPS`. The other apps (`architects`, `applications`, `offers`, `wallet`, `reviews`) do **not** exist yet — each later chunk adds its own app to `INSTALLED_APPS` in the step where it runs `startapp`, right before that app's first `makemigrations`. Never add an app to `INSTALLED_APPS` before its directory exists — Django imports every entry at startup and `manage.py test`/`migrate` will fail with `ModuleNotFoundError` for the whole project, not just a missing-app error.
- Set `AUTH_USER_MODEL = 'accounts.User'`
- Set `LANGUAGE_CODE = 'uz'`, `TIME_ZONE = 'Asia/Tashkent'`
- Add media config:
```python
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
```
- Add `TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates']`
- Set `LOGIN_URL = 'accounts:login'`, `LOGIN_REDIRECT_URL = 'dashboard'`, `LOGOUT_REDIRECT_URL = 'accounts:login'`

Edit `poydevor/urls.py` to include `path('media/...', ...)` static serving in DEBUG and `path('', include('accounts.urls'))`.

- [ ] **Step 4: Write failing test for custom User model**

`accounts/tests/__init__.py` (empty), `accounts/tests/test_models.py`:

```python
from django.test import TestCase
from accounts.models import User


class UserModelTests(TestCase):
    def test_create_user_with_phone(self):
        user = User.objects.create_user(
            phone="+998901234567", password="testpass123",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.assertEqual(user.phone, "+998901234567")
        self.assertTrue(user.check_password("testpass123"))
        self.assertEqual(user.role, User.Role.USER)

    def test_phone_is_unique(self):
        User.objects.create_user(
            phone="+998901234567", password="pass1",
            first_name="A", last_name="B", role=User.Role.USER,
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                phone="+998901234567", password="pass2",
                first_name="C", last_name="D", role=User.Role.ARCHITECT,
            )

    def test_role_choices(self):
        self.assertEqual(User.Role.USER, "user")
        self.assertEqual(User.Role.ARCHITECT, "architect")
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python manage.py test accounts.tests.test_models -v 2`
Expected: FAIL (ImportError — `accounts.models.User` doesn't exist yet)

- [ ] **Step 6: Implement User model and manager**

`accounts/managers.py`:

```python
from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        if not phone:
            raise ValueError("Telefon raqami kiritilishi shart")
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "user")
        return self._create_user(phone, password, **extra_fields)
```

`accounts/models.py`:

```python
from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.managers import UserManager


class User(AbstractUser):
    username = None

    class Role(models.TextChoices):
        USER = "user", "Foydalanuvchi"
        ARCHITECT = "architect", "Arxitektor"

    phone = models.CharField(max_length=20, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name", "role"]

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone})"
```

- [ ] **Step 7: Run makemigrations and migrate**

Run: `python manage.py makemigrations accounts && python manage.py migrate`
Expected: migration file created, applies cleanly

- [ ] **Step 8: Run test to verify it passes**

Run: `python manage.py test accounts.tests.test_models -v 2`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add manage.py poydevor accounts requirements.txt .gitignore
git commit -m "feat: custom phone-based User model"
```

(Create `.gitignore` first with `venv/`, `db.sqlite3`, `media/`, `__pycache__/`, `*.pyc` before this commit.)

- [ ] **Step 10: Write failing tests for signup/login views**

`accounts/tests/test_views.py`:

```python
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class SignupViewTests(TestCase):
    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "Aziz", "last_name": "Karimov",
            "phone": "+998901112233", "password": "testpass123",
            "role": User.Role.USER,
        })
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(phone="+998901112233")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_duplicate_phone_shows_error(self):
        User.objects.create_user(
            phone="+998901112233", password="x",
            first_name="A", last_name="B", role=User.Role.USER,
        )
        response = self.client.post(reverse("accounts:signup"), {
            "first_name": "C", "last_name": "D",
            "phone": "+998901112233", "password": "testpass123",
            "role": User.Role.USER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "band")  # "band" = "taken" in Uzbek error copy


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901112233", password="testpass123",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )

    def test_login_with_correct_credentials(self):
        response = self.client.post(reverse("accounts:login"), {
            "phone": "+998901112233", "password": "testpass123",
        })
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(reverse("accounts:login"), {
            "phone": "+998901112233", "password": "wrong",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
```

- [ ] **Step 11: Run tests to verify they fail**

Run: `python manage.py test accounts.tests.test_views -v 2`
Expected: FAIL (NoReverseMatch — `accounts:signup` URL doesn't exist yet)

- [ ] **Step 12: Implement forms, views, urls**

`accounts/forms.py`:

```python
from django import forms
from django.contrib.auth import authenticate

from accounts.models import User


class SignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Parol")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "role"]
        widgets = {"role": forms.RadioSelect}
        labels = {
            "first_name": "Ism", "last_name": "Familiya",
            "phone": "Telefon raqami",
        }

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Bu telefon raqami band, boshqasini kiriting.")
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    phone = forms.CharField(label="Telefon raqami")
    password = forms.CharField(widget=forms.PasswordInput, label="Parol")

    def clean(self):
        cleaned = super().clean()
        user = authenticate(phone=cleaned.get("phone"), password=cleaned.get("password"))
        if user is None:
            raise forms.ValidationError("Telefon raqami yoki parol noto'g'ri.")
        cleaned["user"] = user
        return cleaned
```

`accounts/views.py`:

```python
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.shortcuts import redirect, render

from accounts.forms import LoginForm, SignupForm
from accounts.models import User


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            if user.role == User.Role.ARCHITECT:
                return redirect("architects:onboarding")
            return redirect("dashboard")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            auth_login(request, form.cleaned_data["user"])
            return redirect("dashboard")
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    return redirect("accounts:login")
```

`accounts/urls.py`:

```python
from django.urls import path

from accounts import views

app_name = "accounts"
urlpatterns = [
    path("ro'yxatdan-o'tish/", views.signup, name="signup"),
    path("kirish/", views.login_view, name="login"),
    path("chiqish/", views.logout_view, name="logout"),
]
```

Register in `poydevor/urls.py`: `path("", include("accounts.urls"))`.

Also add a minimal `dashboard` view in `poydevor/urls.py` / a small `core` view that redirects to the right role-specific dashboard (`applications:dashboard` for users, `architects:dashboard` for architects) — implemented properly once those apps exist in Chunk 3/2; for now stub it as a view returning a simple "Boshqaruv paneli" placeholder template so `LOGIN_REDIRECT_URL` resolves. Create `poydevor/views.py` with:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def dashboard_redirect(request):
    if request.user.role == request.user.Role.ARCHITECT:
        return redirect("architects:dashboard")
    return redirect("applications:dashboard")
```

Wire `path("boshqaruv/", dashboard_redirect, name="dashboard")` in `poydevor/urls.py` (this will 404 until Chunks 2/3 add the target URLs — acceptable at this stage since Step 11's tests only assert a 302 redirect, not resolution of the target).

- [ ] **Step 13: Create base template and signup/login templates**

`templates/base.html` — Tailwind (CDN) + Alpine.js (CDN) shell, white background, professional look, nav with Poydevor logo/name, login/signup or user menu depending on auth state, `{% block content %}`.

```html
<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Poydevor{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-white text-gray-900 min-h-screen flex flex-col">
  <nav class="border-b border-gray-100 px-6 py-4 flex justify-between items-center">
    <a href="/" class="text-xl font-semibold text-slate-800">Poydevor</a>
    <div class="flex gap-4 text-sm">
      {% if user.is_authenticated %}
        <a href="{% url 'dashboard' %}" class="text-slate-600 hover:text-slate-900">Boshqaruv paneli</a>
        <a href="{% url 'accounts:logout' %}" class="text-slate-600 hover:text-slate-900">Chiqish</a>
      {% else %}
        <a href="{% url 'accounts:login' %}" class="text-slate-600 hover:text-slate-900">Kirish</a>
        <a href="{% url 'accounts:signup' %}" class="text-slate-800 font-medium hover:text-slate-900">Ro'yxatdan o'tish</a>
      {% endif %}
    </div>
  </nav>
  <main class="flex-1 max-w-6xl mx-auto w-full px-6 py-10">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`templates/accounts/signup.html` — extends base, renders `SignupForm` fields with Tailwind input styling (rounded border, focus ring), role field as two large clickable cards ("Men foydalanuvchiman" / "Men arxitektorman") styled via Alpine.js `x-model` bound to the underlying radio inputs.

`templates/accounts/login.html` — extends base, simple centered card with phone + password fields, link to signup.

- [ ] **Step 14: Run tests to verify they pass**

Run: `python manage.py test accounts -v 2`
Expected: PASS (all accounts tests)

- [ ] **Step 15: Register User in admin**

`accounts/admin.py`:

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["phone"]
    list_display = ["phone", "first_name", "last_name", "role", "is_staff"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Shaxsiy ma'lumot", {"fields": ("first_name", "last_name", "role")}),
        ("Ruxsatlar", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )
    search_fields = ["phone", "first_name", "last_name"]
```

- [ ] **Step 16: Commit**

```bash
git add accounts templates poydevor
git commit -m "feat: signup/login views and templates"
```

---

## Chunk 2: architects app (profile, portfolio, styles, skills)

**Files:**
- Create: `architects/models.py`, `architects/forms.py`, `architects/views.py`, `architects/urls.py`, `architects/admin.py`
- Create: `templates/architects/onboarding.html`, `templates/architects/dashboard.html`, `templates/architects/portfolio_form.html`, `templates/architects/public_list.html`, `templates/architects/public_detail.html`, `templates/architects/project_form.html`, `templates/architects/project_image_form.html`
- Test: `architects/tests/test_models.py`, `architects/tests/test_views.py`

- [ ] **Step 1: Write failing tests for Style/Skill/ArchitectProfile/PortfolioProject/PortfolioImage models**

`architects/tests/test_models.py`:

```python
from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style


class ArchitectModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )

    def test_create_architect_profile_with_wallet(self):
        profile = ArchitectProfile.objects.create(user=self.user, bio="10 yillik tajriba")
        self.assertEqual(profile.rating, 0)
        self.assertEqual(profile.completed_projects_count, 0)
        self.assertEqual(str(profile), "Nodir Yusupov")

    def test_portfolio_project_with_images_ordering(self):
        profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        style = Style.objects.create(name="Zamonaviy")
        project = PortfolioProject.objects.create(
            architect=profile, title="Villa loyihasi", description="...", style=style,
        )
        img2 = PortfolioImage.objects.create(project=project, image="portfolio/2.jpg", order=2)
        img1 = PortfolioImage.objects.create(project=project, image="portfolio/1.jpg", order=1)
        ordered = list(project.images.all())
        self.assertEqual(ordered, [img1, img2])

    def test_skill_and_style_m2m(self):
        profile = ArchitectProfile.objects.create(user=self.user, bio="x")
        skill = Skill.objects.create(name="3D vizualizatsiya")
        style = Style.objects.create(name="Minimalizm")
        profile.skills.add(skill)
        profile.styles.add(style)
        self.assertIn(skill, profile.skills.all())
        self.assertIn(style, profile.styles.all())
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test architects.tests.test_models -v 2`
Expected: FAIL (ModuleNotFoundError / app not created)

- [ ] **Step 3: Create the app and implement models**

```bash
python manage.py startapp architects
```

`architects/models.py`:

```python
from django.conf import settings
from django.db import models


class Style(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ArchitectProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="architect_profile")
    bio = models.TextField()
    telegram_username = models.CharField(max_length=50, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    completed_projects_count = models.PositiveIntegerField(default=0)
    styles = models.ManyToManyField(Style, related_name="architects", blank=True)
    skills = models.ManyToManyField(Skill, related_name="architects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"


class PortfolioProject(models.Model):
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, related_name="projects")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class PortfolioImage(models.Model):
    project = models.ForeignKey(PortfolioProject, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="portfolio/")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
```

- [ ] **Step 4: Add app, migrate**

Add `"architects"` to `INSTALLED_APPS`.

Run: `python manage.py makemigrations architects && python manage.py migrate`

- [ ] **Step 5: Run tests to verify pass**

Run: `python manage.py test architects.tests.test_models -v 2`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add architects poydevor/settings.py
git commit -m "feat: architect profile, portfolio, style/skill models"
```

- [ ] **Step 7: Write failing tests for onboarding + portfolio views**

`architects/tests/test_views.py`:

```python
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile, PortfolioProject, Skill, Style


class OnboardingViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.client.force_login(self.user)
        self.skill = Skill.objects.create(name="3D vizualizatsiya")

    def test_onboarding_creates_profile(self):
        response = self.client.post(reverse("architects:onboarding"), {
            "bio": "10 yillik tajriba", "skills": [self.skill.id],
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ArchitectProfile.objects.filter(user=self.user).exists())


class PublicListViewTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.modern = Style.objects.create(name="Zamonaviy")
        self.classic = Style.objects.create(name="Klassik")
        self.profile.styles.add(self.modern)

    def test_list_shows_architect(self):
        response = self.client.get(reverse("architects:list"))
        self.assertContains(response, "Nodir")

    def test_filter_by_style_excludes_non_matching(self):
        other_user = User.objects.create_user(
            phone="+998907654321", password="x",
            first_name="Malika", last_name="Rashidova", role=User.Role.ARCHITECT,
        )
        other_profile = ArchitectProfile.objects.create(user=other_user, bio="y")
        other_profile.styles.add(self.classic)

        response = self.client.get(reverse("architects:list"), {"style": self.modern.id})
        self.assertContains(response, "Nodir")
        self.assertNotContains(response, "Malika")
```

- [ ] **Step 8: Run to verify failure**

Run: `python manage.py test architects.tests.test_views -v 2`
Expected: FAIL (NoReverseMatch)

- [ ] **Step 9: Implement forms, views, urls**

`architects/forms.py`:

```python
from django import forms

from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject


class ArchitectProfileForm(forms.ModelForm):
    class Meta:
        model = ArchitectProfile
        fields = ["bio", "telegram_username", "avatar", "styles", "skills"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
            "styles": forms.CheckboxSelectMultiple,
            "skills": forms.CheckboxSelectMultiple,
        }


class PortfolioProjectForm(forms.ModelForm):
    class Meta:
        model = PortfolioProject
        fields = ["title", "description", "style", "order"]


class PortfolioImageForm(forms.ModelForm):
    class Meta:
        model = PortfolioImage
        fields = ["image", "order"]
```

`architects/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from architects.forms import ArchitectProfileForm, PortfolioImageForm, PortfolioProjectForm
from architects.models import ArchitectProfile, Style


@login_required
def onboarding(request):
    if hasattr(request.user, "architect_profile"):
        return redirect("architects:dashboard")
    if request.method == "POST":
        form = ArchitectProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            form.save_m2m()
            return redirect("architects:dashboard")
    else:
        form = ArchitectProfileForm()
    return render(request, "architects/onboarding.html", {"form": form})


@login_required
def dashboard(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    return render(request, "architects/dashboard.html", {"profile": profile})


@login_required
def portfolio_edit(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    if request.method == "POST":
        form = ArchitectProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("architects:dashboard")
    else:
        form = ArchitectProfileForm(instance=profile)
    return render(request, "architects/portfolio_form.html", {"form": form, "profile": profile})


@login_required
def project_create(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    if request.method == "POST":
        form = PortfolioProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.architect = profile
            project.save()
            return redirect("architects:dashboard")
    else:
        form = PortfolioProjectForm()
    return render(request, "architects/project_form.html", {"form": form})


@login_required
def project_image_add(request, project_id):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    project = get_object_or_404(profile.projects, id=project_id)
    if request.method == "POST":
        form = PortfolioImageForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.project = project
            image.save()
            return redirect("architects:dashboard")
    else:
        form = PortfolioImageForm()
    return render(request, "architects/project_image_form.html", {"form": form, "project": project})


def public_list(request):
    profiles = ArchitectProfile.objects.all().prefetch_related("projects__images", "styles")
    style_id = request.GET.get("style")
    if style_id:
        profiles = profiles.filter(styles__id=style_id).distinct()
    styles = Style.objects.all()
    return render(request, "architects/public_list.html", {"profiles": profiles, "styles": styles, "selected_style": style_id})


def public_detail(request, pk):
    profile = get_object_or_404(ArchitectProfile.objects.prefetch_related("projects__images", "styles", "skills"), pk=pk)
    style_id = request.GET.get("style")
    projects = profile.projects.all()
    if style_id:
        projects = projects.filter(style_id=style_id)
    return render(request, "architects/public_detail.html", {"profile": profile, "projects": projects, "selected_style": style_id})
```

`architects/urls.py`:

```python
from django.urls import path

from architects import views

app_name = "architects"
urlpatterns = [
    path("arxitektorlar/", views.public_list, name="list"),
    path("arxitektorlar/<int:pk>/", views.public_detail, name="detail"),
    path("panel/ro'yxatdan-o'tish/", views.onboarding, name="onboarding"),
    path("panel/", views.dashboard, name="dashboard"),
    path("panel/profil/", views.portfolio_edit, name="portfolio_edit"),
    path("panel/loyiha/qo'shish/", views.project_create, name="project_create"),
    path("panel/loyiha/<int:project_id>/rasm-qo'shish/", views.project_image_add, name="project_image_add"),
]
```

Register in `poydevor/urls.py`: `path("", include("architects.urls"))`.

- [ ] **Step 10: Create templates**

`templates/architects/onboarding.html` — form for bio, telegram, avatar, styles (checkbox pills), skills (checkbox pills), submit "Profilni yaratish".

`templates/architects/public_list.html` — style filter bar at top (links/buttons that set `?style=`), responsive grid of architect cards. Card: `x-data` Alpine component that auto-advances through `profile.projects` images every 3s via `setInterval`, rating stars, name, "N loyiha yakunlangan", placeholder icon (simple SVG person/building icon in a gray circle) when no images/avatar exist.

`templates/architects/public_detail.html` — avatar/placeholder, name, rating, skills as pills, style filter (re-filters `projects` shown below via the `?style=` query param already handled server-side), portfolio projects grid each with its own image carousel, "Ariza yuborish" button linking to the offers app's send-application flow (Chunk 4).

`templates/architects/dashboard.html` — three-tab shell (Portfolio / Arizalar / Ochiq e'lonlar) using Alpine `x-data="{tab: 'portfolio'}"`; Portfolio tab lists profile info + edit link + "Loyiha qo'shish" + per-project "Rasm qo'shish"; other two tabs are stubs here (`{% comment %}filled in Chunk 4/5{% endcomment %}`) until Offers/Wallet chunks add their content blocks via `{% include %}`.

`templates/architects/project_form.html` — extends base, renders `PortfolioProjectForm` (title, description, style, order), submit "Loyihani saqlash".

`templates/architects/project_image_form.html` — extends base, shows the project's title for context, renders `PortfolioImageForm` (image file input, order), submit "Rasmni qo'shish".

- [ ] **Step 11: Run tests to verify pass**

Run: `python manage.py test architects -v 2`
Expected: PASS

- [ ] **Step 12: Register in admin**

`architects/admin.py`:

```python
from django.contrib import admin

from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Skill, Style


class PortfolioImageInline(admin.TabularInline):
    model = PortfolioImage
    extra = 1


class PortfolioProjectInline(admin.TabularInline):
    model = PortfolioProject
    extra = 0


@admin.register(ArchitectProfile)
class ArchitectProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "rating", "completed_projects_count"]
    inlines = [PortfolioProjectInline]


@admin.register(PortfolioProject)
class PortfolioProjectAdmin(admin.ModelAdmin):
    inlines = [PortfolioImageInline]


admin.site.register(Style)
admin.site.register(Skill)
```

- [ ] **Step 13: Commit**

```bash
git add architects templates poydevor
git commit -m "feat: architect onboarding, portfolio management, public listing"
```

---

## Chunk 3: applications app (project postings)

**Files:**
- Create: `applications/models.py`, `applications/forms.py`, `applications/views.py`, `applications/urls.py`, `applications/admin.py`
- Create: `templates/applications/post_form.html`, `templates/applications/dashboard.html`, `templates/applications/detail.html`
- Test: `applications/tests/test_models.py`, `applications/tests/test_views.py`

- [ ] **Step 1: Write failing model tests**

`applications/tests/test_models.py`:

```python
from django.test import TestCase

from accounts.models import User
from applications.models import Application


class ApplicationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )

    def test_create_application_with_known_size(self):
        app = Application.objects.create(
            owner=self.user, size_m2=120, rooms_count=4, location="Toshkent",
        )
        self.assertEqual(app.status, Application.Status.OPEN)
        self.assertIsNotNone(app.size_m2)

    def test_create_application_with_unknown_size(self):
        app = Application.objects.create(
            owner=self.user, size_m2=None, rooms_count=3, location="Samarqand",
        )
        self.assertIsNone(app.size_m2)
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test applications.tests.test_models -v 2`
Expected: FAIL

- [ ] **Step 3: Create app and implement model**

```bash
python manage.py startapp applications
```

`applications/models.py`:

```python
from django.conf import settings
from django.db import models

from architects.models import Style


class Application(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Ochiq"
        IN_PROGRESS = "in_progress", "Jarayonda"
        CLOSED = "closed", "Yakunlangan"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    size_m2 = models.PositiveIntegerField(null=True, blank=True)
    rooms_count = models.PositiveSmallIntegerField()
    location = models.CharField(max_length=100)
    interior_style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True, related_name="applications")
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    plan_pdf = models.FileField(upload_to="plans/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.location} — {self.rooms_count} xona"
```

- [ ] **Step 4: Add app, migrate**

Add `"applications"` to `INSTALLED_APPS`.

Run: `python manage.py makemigrations applications && python manage.py migrate`

- [ ] **Step 5: Run tests to verify pass**

Run: `python manage.py test applications.tests.test_models -v 2`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add applications poydevor/settings.py
git commit -m "feat: Application model for user project postings"
```

- [ ] **Step 7: Write failing view tests**

`applications/tests/test_views.py`:

```python
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application


class PostApplicationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_post_application_known_size(self):
        response = self.client.post(reverse("applications:post"), {
            "size_unknown": "", "size_m2": 100, "rooms_count": 3,
            "location": "Toshkent", "budget": "", "interior_style": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Application.objects.count(), 1)

    def test_post_application_unknown_size(self):
        response = self.client.post(reverse("applications:post"), {
            "size_unknown": "on", "size_m2": "", "rooms_count": 5,
            "location": "Buxoro", "budget": "", "interior_style": "",
        })
        self.assertEqual(response.status_code, 302)
        app = Application.objects.get()
        self.assertIsNone(app.size_m2)


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.client.force_login(self.user)

    def test_dashboard_lists_own_applications(self):
        Application.objects.create(owner=self.user, rooms_count=2, location="Andijon")
        response = self.client.get(reverse("applications:dashboard"))
        self.assertContains(response, "Andijon")
```

- [ ] **Step 8: Run to verify failure**

Run: `python manage.py test applications.tests.test_views -v 2`
Expected: FAIL (NoReverseMatch)

- [ ] **Step 9: Implement form (with size_unknown toggle), views, urls**

`applications/forms.py`:

```python
from django import forms

from applications.models import Application


class ApplicationForm(forms.ModelForm):
    size_unknown = forms.BooleanField(required=False, label="Bilmayman, taxminan hisoblang")

    class Meta:
        model = Application
        fields = ["size_m2", "size_unknown", "rooms_count", "location", "interior_style", "budget", "plan_pdf"]
        labels = {
            "size_m2": "Maydon (m²)", "rooms_count": "Xonalar soni",
            "location": "Manzil", "interior_style": "Interyer uslubi (ixtiyoriy)",
            "budget": "Byudjet (ixtiyoriy)", "plan_pdf": "Uy rejasi, PDF (ixtiyoriy)",
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("size_unknown"):
            cleaned["size_m2"] = None
        elif not cleaned.get("size_m2"):
            self.add_error("size_m2", "Maydonni kiriting yoki 'Bilmayman' belgisini qo'ying.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("size_unknown"):
            instance.size_m2 = None
        if commit:
            instance.save()
        return instance
```

`applications/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from applications.forms import ApplicationForm
from applications.models import Application


@login_required
def post_application(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.owner = request.user
            application.save()
            return redirect("applications:detail", pk=application.pk)
    else:
        form = ApplicationForm()
    return render(request, "applications/post_form.html", {"form": form})


@login_required
def dashboard(request):
    applications = request.user.applications.all()
    return render(request, "applications/dashboard.html", {"applications": applications})


@login_required
def detail(request, pk):
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    return render(request, "applications/detail.html", {"application": application})
```

`applications/urls.py`:

```python
from django.urls import path

from applications import views

app_name = "applications"
urlpatterns = [
    path("elon/joylashtirish/", views.post_application, name="post"),
    path("panel/", views.dashboard, name="dashboard"),
    path("elon/<int:pk>/", views.detail, name="detail"),
]
```

Register in `poydevor/urls.py`: `path("", include("applications.urls"))`.

- [ ] **Step 10: Create templates**

`templates/applications/post_form.html` — form with `size_unknown` checkbox (Alpine `x-data="{unknown: false}"` toggling disabled/hidden state of `size_m2` field), rooms count, location, interior style select, budget, plan PDF file input, submit "E'lonni joylashtirish".

`templates/applications/dashboard.html` — list of the user's own applications as cards (location, rooms, status badge), link to post a new one, link to each detail page.

`templates/applications/detail.html` — full application details; placeholder section `{% comment %}offers list added in Chunk 4{% endcomment %}` for now.

- [ ] **Step 11: Run tests to verify pass**

Run: `python manage.py test applications -v 2`
Expected: PASS

- [ ] **Step 12: Register in admin**

`applications/admin.py`:

```python
from django.contrib import admin

from applications.models import Application

admin.site.register(Application)
```

- [ ] **Step 13: Commit**

```bash
git add applications templates poydevor
git commit -m "feat: post/list/view project applications"
```

---

## Chunk 4: wallet app (coins)

**Files:**
- Create: `wallet/models.py`, `wallet/services.py`, `wallet/views.py`, `wallet/urls.py`, `wallet/admin.py`
- Create: `templates/wallet/dashboard.html`
- Test: `wallet/tests/test_models.py`, `wallet/tests/test_services.py`, `wallet/tests/test_views.py`

- [ ] **Step 1: Write failing model tests**

`wallet/tests/test_models.py`:

```python
from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import Wallet


class WalletModelTests(TestCase):
    def test_wallet_created_with_zero_balance(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        profile = ArchitectProfile.objects.create(user=user, bio="x")
        wallet = Wallet.objects.create(architect=profile)
        self.assertEqual(wallet.balance, 0)
```

- [ ] **Step 2: Run to verify failure, then create app and model**

```bash
python manage.py test wallet.tests.test_models -v 2   # expect FAIL
python manage.py startapp wallet
```

`wallet/models.py`:

```python
from django.db import models

from architects.models import ArchitectProfile


class Wallet(models.Model):
    architect = models.OneToOneField(ArchitectProfile, on_delete=models.CASCADE, related_name="wallet")
    balance = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.architect} — {self.balance} tanga"


class CoinTransaction(models.Model):
    class Reason(models.TextChoices):
        TOPUP = "topup", "To'ldirish"
        OFFER_SPEND = "offer_spend", "Ariza uchun sarflandi"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    amount = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
```

- [ ] **Step 3: Add app, migrate, run tests**

Add `"wallet"` to `INSTALLED_APPS`.

Run: `python manage.py makemigrations wallet && python manage.py migrate && python manage.py test wallet.tests.test_models -v 2`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add wallet poydevor/settings.py
git commit -m "feat: Wallet and CoinTransaction models"
```

- [ ] **Step 5: Write failing tests for wallet service functions**

`wallet/tests/test_services.py`:

```python
from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import CoinTransaction, Wallet
from wallet.services import InsufficientCoinsError, spend_coins, topup_coins


class WalletServiceTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)

    def test_topup_increases_balance_and_logs_transaction(self):
        topup_coins(self.wallet, 20)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 20)
        self.assertEqual(
            CoinTransaction.objects.filter(wallet=self.wallet, reason=CoinTransaction.Reason.TOPUP).count(), 1,
        )

    def test_spend_decreases_balance(self):
        topup_coins(self.wallet, 20)
        spend_coins(self.wallet, 20)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)

    def test_spend_more_than_balance_raises(self):
        with self.assertRaises(InsufficientCoinsError):
            spend_coins(self.wallet, 20)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)
```

- [ ] **Step 6: Run to verify failure**

Run: `python manage.py test wallet.tests.test_services -v 2`
Expected: FAIL (ImportError)

- [ ] **Step 7: Implement services**

Note: `select_for_update()` is a silent no-op on SQLite (the dev DB here) — it only actually locks rows on Postgres/MySQL. The row-locking pattern below is still correct to write now since it's what makes the code race-safe once deployed on Postgres; just don't expect it to prevent races in local SQLite testing.

`wallet/services.py`:

```python
from django.db import transaction

from wallet.models import CoinTransaction, Wallet


class InsufficientCoinsError(Exception):
    pass


@transaction.atomic
def topup_coins(wallet: Wallet, amount: int) -> None:
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    locked.balance += amount
    locked.save(update_fields=["balance"])
    CoinTransaction.objects.create(wallet=locked, amount=amount, reason=CoinTransaction.Reason.TOPUP)
    wallet.balance = locked.balance


@transaction.atomic
def spend_coins(wallet: Wallet, amount: int) -> None:
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    if locked.balance < amount:
        raise InsufficientCoinsError("Tangalar yetarli emas")
    locked.balance -= amount
    locked.save(update_fields=["balance"])
    CoinTransaction.objects.create(wallet=locked, amount=-amount, reason=CoinTransaction.Reason.OFFER_SPEND)
    wallet.balance = locked.balance
```

(The `models_f_expr_safe_add` helper is trivial here — kept as a named function only so intent is explicit; feel free to inline it during implementation if it reads more clearly as `wallet.balance + amount` directly.)

- [ ] **Step 8: Run tests to verify pass**

Run: `python manage.py test wallet.tests.test_services -v 2`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add wallet
git commit -m "feat: wallet topup/spend services with insufficient-balance guard"
```

- [ ] **Step 10: Write failing tests for buy-coins view**

`wallet/tests/test_views.py`:

```python
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import Wallet


class BuyCoinsViewTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)
        self.client.force_login(user)

    def test_buy_coins_credits_balance(self):
        response = self.client.post(reverse("wallet:buy"), {"package": "20"})
        self.assertEqual(response.status_code, 302)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 20)
```

- [ ] **Step 11: Run to verify failure, then implement view/urls**

Run: `python manage.py test wallet.tests.test_views -v 2` — expect FAIL

`wallet/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from wallet.models import Wallet
from wallet.services import topup_coins

PACKAGES = {"20": 20, "40": 40, "100": 100}


@login_required
def dashboard(request):
    wallet = get_object_or_404(Wallet, architect__user=request.user)
    return render(request, "wallet/dashboard.html", {"wallet": wallet, "packages": PACKAGES})


@login_required
def buy_coins(request):
    wallet = get_object_or_404(Wallet, architect__user=request.user)
    if request.method == "POST":
        amount = PACKAGES.get(request.POST.get("package"))
        if amount:
            topup_coins(wallet, amount)
    return redirect("wallet:dashboard")
```

`wallet/urls.py`:

```python
from django.urls import path

from wallet import views

app_name = "wallet"
urlpatterns = [
    path("panel/hamyon/", views.dashboard, name="dashboard"),
    path("panel/hamyon/sotib-olish/", views.buy_coins, name="buy"),
]
```

Register in `poydevor/urls.py`. Also ensure `ArchitectProfile` creation (Chunk 2 `onboarding` view) creates a `Wallet` for the new profile — add this line to `architects/views.py::onboarding` after `profile.save()`: `Wallet.objects.create(architect=profile)` (import `from wallet.models import Wallet` — this creates a real cross-app dependency at save time, acceptable since wallet is a core part of every architect account).

- [ ] **Step 12: Create template**

`templates/wallet/dashboard.html` — balance display, package buttons (20/40/100 coins ≈ $5/$10/$25) each posting to `wallet:buy`, transaction history table.

- [ ] **Step 13: Run tests to verify pass**

Run: `python manage.py test wallet -v 2`
Expected: PASS

- [ ] **Step 14: Register in admin, commit**

`wallet/admin.py`:

```python
from django.contrib import admin

from wallet.models import CoinTransaction, Wallet

admin.site.register(Wallet)
admin.site.register(CoinTransaction)
```

```bash
git add wallet architects/views.py templates poydevor
git commit -m "feat: buy-coins flow and wallet dashboard"
```

---

## Chunk 5: offers app (send/accept/reject/complete)

**Files:**
- Create: `offers/models.py`, `offers/services.py`, `offers/views.py`, `offers/urls.py`, `offers/admin.py`
- Modify: `templates/applications/detail.html`, `templates/architects/public_detail.html`, `templates/architects/dashboard.html`
- Create: `templates/offers/send_form.html`, `templates/offers/apply_error.html`
- Test: `offers/tests/test_models.py`, `offers/tests/test_services.py`, `offers/tests/test_views.py`

- [ ] **Step 1: Write failing model tests**

`offers/tests/test_models.py`:

```python
from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer


class OfferModelTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x",
            first_name="Aziz", last_name="Karimov", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")

    def test_create_pending_offer(self):
        offer = Offer.objects.create(
            application=self.application, architect=self.architect,
            source=Offer.Source.ARCHITECT_APPLIED,
        )
        self.assertEqual(offer.status, Offer.Status.PENDING)
```

- [ ] **Step 2: Run to verify failure, create app, implement model**

```bash
python manage.py test offers.tests.test_models -v 2   # expect FAIL
python manage.py startapp offers
```

`offers/models.py`:

```python
from django.db import models

from applications.models import Application
from architects.models import ArchitectProfile


class Offer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        ACCEPTED = "accepted", "Qabul qilindi"
        REJECTED = "rejected", "Rad etildi"
        COMPLETED = "completed", "Yakunlandi"

    class Source(models.TextChoices):
        ARCHITECT_APPLIED = "architect_applied", "Arxitektor o'zi qatnashdi"
        USER_INVITED = "user_invited", "Foydalanuvchi taklif qildi"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="offers")
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="offers")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=20, choices=Source.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "architect"],
                condition=models.Q(status="pending"),
                name="unique_pending_offer_per_application_architect",
            ),
        ]
```

Add `"offers"` to `INSTALLED_APPS`.

Run: `python manage.py makemigrations offers && python manage.py migrate && python manage.py test offers.tests.test_models -v 2`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add offers poydevor/settings.py
git commit -m "feat: Offer model linking applications and architects"
```

- [ ] **Step 4: Write failing tests for offer services (the core business rules)**

`offers/tests/test_services.py`:

```python
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from offers.services import (
    MaxArchitectsReachedError,
    accept_offer,
    complete_offer,
    reject_offer,
    send_offer,
)
from wallet.models import Wallet
from wallet.services import InsufficientCoinsError, topup_coins


class SendOfferTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        self.architects = []
        for i in range(4):
            u = User.objects.create_user(
                phone=f"+99890000000{i}", password="x", first_name=f"Arx{i}", last_name="Y", role=User.Role.ARCHITECT,
            )
            profile = ArchitectProfile.objects.create(user=u, bio="x")
            wallet = Wallet.objects.create(architect=profile)
            topup_coins(wallet, 100)
            self.architects.append(profile)

    def test_architect_applied_spends_20_coins(self):
        offer = send_offer(self.application, self.architects[0], source=Offer.Source.ARCHITECT_APPLIED)
        self.architects[0].wallet.refresh_from_db()
        self.assertEqual(self.architects[0].wallet.balance, 80)
        self.assertEqual(offer.status, Offer.Status.PENDING)

    def test_fourth_architect_applied_offer_blocked(self):
        for profile in self.architects[:3]:
            send_offer(self.application, profile, source=Offer.Source.ARCHITECT_APPLIED)
        with self.assertRaises(MaxArchitectsReachedError):
            send_offer(self.application, self.architects[3], source=Offer.Source.ARCHITECT_APPLIED)
        self.architects[3].wallet.refresh_from_db()
        self.assertEqual(self.architects[3].wallet.balance, 100)  # not charged

    def test_insufficient_coins_blocks_offer(self):
        u = User.objects.create_user(
            phone="+998909999999", password="x", first_name="Poor", last_name="Y", role=User.Role.ARCHITECT,
        )
        poor_profile = ArchitectProfile.objects.create(user=u, bio="x")
        Wallet.objects.create(architect=poor_profile)  # balance 0
        with self.assertRaises(InsufficientCoinsError):
            send_offer(self.application, poor_profile, source=Offer.Source.ARCHITECT_APPLIED)

    def test_user_invited_offer_does_not_spend_coins(self):
        offer = send_offer(self.application, self.architects[0], source=Offer.Source.USER_INVITED)
        self.architects[0].wallet.refresh_from_db()
        self.assertEqual(self.architects[0].wallet.balance, 100)
        self.assertEqual(offer.source, Offer.Source.USER_INVITED)


class AcceptRejectOfferTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        self.offers = []
        for i in range(3):
            u = User.objects.create_user(
                phone=f"+99890000000{i}", password="x", first_name=f"Arx{i}", last_name="Y", role=User.Role.ARCHITECT,
            )
            profile = ArchitectProfile.objects.create(user=u, bio="x")
            Wallet.objects.create(architect=profile, balance=100)
            self.offers.append(
                Offer.objects.create(application=self.application, architect=profile, source=Offer.Source.ARCHITECT_APPLIED)
            )

    def test_accept_rejects_siblings_and_moves_application_in_progress(self):
        accept_offer(self.offers[0])
        self.application.refresh_from_db()
        self.offers[1].refresh_from_db()
        self.offers[2].refresh_from_db()
        self.offers[0].refresh_from_db()

        self.assertEqual(self.offers[0].status, Offer.Status.ACCEPTED)
        self.assertEqual(self.offers[1].status, Offer.Status.REJECTED)
        self.assertEqual(self.offers[2].status, Offer.Status.REJECTED)
        self.assertEqual(self.application.status, Application.Status.IN_PROGRESS)

    def test_reject_single_offer_leaves_others_pending(self):
        reject_offer(self.offers[0])
        self.offers[1].refresh_from_db()
        self.assertEqual(self.offers[0].status, Offer.Status.REJECTED)
        self.assertEqual(self.offers[1].status, Offer.Status.PENDING)

    def test_complete_offer_updates_counts_and_application(self):
        accept_offer(self.offers[0])
        complete_offer(self.offers[0])
        self.offers[0].refresh_from_db()
        self.application.refresh_from_db()
        self.offers[0].architect.refresh_from_db()

        self.assertEqual(self.offers[0].status, Offer.Status.COMPLETED)
        self.assertEqual(self.application.status, Application.Status.CLOSED)
        self.assertEqual(self.offers[0].architect.completed_projects_count, 1)
```

- [ ] **Step 5: Run to verify failure**

Run: `python manage.py test offers.tests.test_services -v 2`
Expected: FAIL (ImportError)

- [ ] **Step 6: Implement services**

`offers/services.py`:

```python
from django.db import transaction
from django.utils import timezone

from applications.models import Application
from offers.models import Offer
from wallet.services import spend_coins

OFFER_COST = 20
MAX_ACTIVE_OFFERS_PER_APPLICATION = 3


class MaxArchitectsReachedError(Exception):
    pass


@transaction.atomic
def send_offer(application: Application, architect, source: str) -> Offer:
    pending_count = application.offers.select_for_update().filter(status=Offer.Status.PENDING).count()
    if pending_count >= MAX_ACTIVE_OFFERS_PER_APPLICATION:
        raise MaxArchitectsReachedError("Bu e'longa allaqachon 3 ta arxitektor qatnashmoqda")

    if source == Offer.Source.ARCHITECT_APPLIED:
        spend_coins(architect.wallet, OFFER_COST)

    return Offer.objects.create(application=application, architect=architect, source=source)


@transaction.atomic
def accept_offer(offer: Offer) -> None:
    offer.status = Offer.Status.ACCEPTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])

    offer.application.offers.filter(status=Offer.Status.PENDING).exclude(pk=offer.pk).update(
        status=Offer.Status.REJECTED, decided_at=timezone.now(),
    )

    offer.application.status = Application.Status.IN_PROGRESS
    offer.application.save(update_fields=["status"])


@transaction.atomic
def reject_offer(offer: Offer) -> None:
    offer.status = Offer.Status.REJECTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])


@transaction.atomic
def complete_offer(offer: Offer) -> None:
    offer.status = Offer.Status.COMPLETED
    offer.completed_at = timezone.now()
    offer.save(update_fields=["status", "completed_at"])

    offer.application.status = Application.Status.CLOSED
    offer.application.save(update_fields=["status"])

    architect = offer.architect
    architect.completed_projects_count += 1
    architect.save(update_fields=["completed_projects_count"])
```

- [ ] **Step 7: Run tests to verify pass**

Run: `python manage.py test offers.tests.test_services -v 2`
Expected: PASS (6 tests)

- [ ] **Step 8: Commit**

```bash
git add offers
git commit -m "feat: offer send/accept/reject/complete services with business rules"
```

- [ ] **Step 9: Write failing view tests**

`offers/tests/test_views.py`:

```python
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from wallet.models import Wallet


class SendOfferFromArchitectProfileTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        self.client.force_login(self.owner)

    def test_user_sends_offer_to_architect(self):
        response = self.client.post(
            reverse("offers:send", args=[self.architect.pk]), {"application": self.application.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Offer.objects.filter(application=self.application, architect=self.architect).exists())


class ArchitectRespondTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        self.application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        Wallet.objects.create(architect=self.architect, balance=100)
        self.offer = Offer.objects.create(
            application=self.application, architect=self.architect, source=Offer.Source.USER_INVITED,
        )
        self.client.force_login(architect_user)

    def test_architect_accepts_offer(self):
        response = self.client.post(reverse("offers:respond", args=[self.offer.pk]), {"decision": "accept"})
        self.assertEqual(response.status_code, 302)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, Offer.Status.ACCEPTED)

    def test_architect_rejects_offer(self):
        response = self.client.post(reverse("offers:respond", args=[self.offer.pk]), {"decision": "reject"})
        self.assertEqual(response.status_code, 302)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, Offer.Status.REJECTED)
```

- [ ] **Step 10: Run to verify failure, implement views/urls**

Run: `python manage.py test offers.tests.test_views -v 2` — expect FAIL

`offers/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from offers.services import (
    MaxArchitectsReachedError,
    accept_offer,
    complete_offer,
    reject_offer,
    send_offer,
)
from wallet.services import InsufficientCoinsError


@login_required
def send_from_architect_profile(request, architect_pk):
    architect = get_object_or_404(ArchitectProfile, pk=architect_pk)
    user_applications = request.user.applications.filter(status=Application.Status.OPEN)
    error = None
    if request.method == "POST":
        application = get_object_or_404(user_applications, pk=request.POST.get("application"))
        try:
            send_offer(application, architect, source=Offer.Source.USER_INVITED)
            return redirect("applications:detail", pk=application.pk)
        except MaxArchitectsReachedError as e:
            error = str(e)
    return render(request, "offers/send_form.html", {
        "architect": architect, "applications": user_applications, "error": error,
    })


@login_required
def architect_apply(request, application_pk):
    application = get_object_or_404(Application, pk=application_pk, status=Application.Status.OPEN)
    architect = get_object_or_404(ArchitectProfile, user=request.user)
    try:
        send_offer(application, architect, source=Offer.Source.ARCHITECT_APPLIED)
    except (MaxArchitectsReachedError, InsufficientCoinsError) as e:
        return render(request, "offers/apply_error.html", {"error": str(e), "application": application})
    except IntegrityError:
        # Double-submit: this architect already has a pending offer on this application
        # (hits the partial unique constraint) — treat it the same as the max-reached case.
        return render(request, "offers/apply_error.html", {
            "error": "Siz bu e'longa allaqachon ariza yubordingiz.", "application": application,
        })
    return redirect("architects:dashboard")


@login_required
def respond(request, offer_pk):
    offer = get_object_or_404(Offer, pk=offer_pk, architect__user=request.user, status=Offer.Status.PENDING)
    if request.method == "POST":
        if request.POST.get("decision") == "accept":
            accept_offer(offer)
        else:
            reject_offer(offer)
    return redirect("architects:dashboard")


@login_required
def user_respond(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.PENDING,
    )
    if request.method == "POST":
        if request.POST.get("decision") == "accept":
            accept_offer(offer)
        else:
            reject_offer(offer)
    return redirect("applications:detail", pk=offer.application.pk)


@login_required
def mark_complete(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.ACCEPTED,
    )
    if request.method == "POST":
        complete_offer(offer)
    return redirect("applications:detail", pk=offer.application.pk)
```

`offers/urls.py`:

```python
from django.urls import path

from offers import views

app_name = "offers"
urlpatterns = [
    path("arxitektor/<int:architect_pk>/ariza-yuborish/", views.send_from_architect_profile, name="send"),
    path("elon/<int:application_pk>/qatnashish/", views.architect_apply, name="architect_apply"),
    path("ariza/<int:offer_pk>/javob/", views.respond, name="respond"),
    path("ariza/<int:offer_pk>/foydalanuvchi-javob/", views.user_respond, name="user_respond"),
    path("ariza/<int:offer_pk>/yakunlash/", views.mark_complete, name="complete"),
]
```

Register in `poydevor/urls.py`.

- [ ] **Step 11: Wire up templates**

Update `templates/architects/public_detail.html`: replace the "Ariza yuborish" button with a link to `offers:send` for the viewed architect, showing the contact-reveal notice ("Arxitektor qabul qilgandan so'ng aloqa ma'lumotlari ko'rinadi") before submit.

Create `templates/offers/send_form.html`: select which of the user's open applications to attach (or link to `applications:post` if none exist), submit button, error display for `MaxArchitectsReachedError`.

Create `templates/offers/apply_error.html`: extends base, shows `{{ error }}` message and a link back to `architects:dashboard` (Ochiq e'lonlar tab) so the architect can try a different posting.

Update `templates/applications/detail.html`: list attached `application.offers.all` — for `pending`/`accepted`/`completed` show architect card + status; for `accepted`/`completed` reveal architect's phone + telegram; show accept/reject buttons (posting to `offers:user_respond`) for each `pending` offer when `source=architect_applied`; show a "Loyihani yakunlash" button (`offers:complete`) when status is `accepted`.

Update `templates/architects/dashboard.html` "Arizalar" tab: list offers where `architect=profile` (both sent and received), with accept/reject buttons (`offers:respond`) for pending `user_invited` offers, revealing the user's phone once accepted. "Ochiq e'lonlar" tab: list open `Application`s with filters, "Qatnashish (20 tanga)" button posting to `offers:architect_apply`.

- [ ] **Step 12: Run tests to verify pass**

Run: `python manage.py test offers -v 2`
Expected: PASS

- [ ] **Step 13: Register in admin, commit**

`offers/admin.py`:

```python
from django.contrib import admin

from offers.models import Offer

admin.site.register(Offer)
```

```bash
git add offers templates poydevor
git commit -m "feat: offer send/respond/complete views and wire into application/architect templates"
```

---

## Chunk 6: reviews app

**Files:**
- Create: `reviews/models.py`, `reviews/services.py`, `reviews/forms.py`, `reviews/views.py`, `reviews/urls.py`, `reviews/admin.py`
- Modify: `templates/applications/detail.html`, `templates/architects/public_detail.html`
- Create: `templates/reviews/review_form.html`
- Test: `reviews/tests/test_models.py`, `reviews/tests/test_services.py`, `reviews/tests/test_views.py`

- [ ] **Step 1: Write failing model tests**

`reviews/tests/test_models.py`:

```python
from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from reviews.models import Review


class ReviewModelTests(TestCase):
    def test_create_review_tied_to_completed_offer(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        offer = Offer.objects.create(
            application=application, architect=architect,
            source=Offer.Source.USER_INVITED, status=Offer.Status.COMPLETED,
        )
        review = Review.objects.create(offer=offer, user=owner, architect=architect, rating=5, comment="Ajoyib!")
        self.assertEqual(review.rating, 5)
```

- [ ] **Step 2: Run to verify failure, create app, implement model**

```bash
python manage.py test reviews.tests.test_models -v 2   # expect FAIL
python manage.py startapp reviews
```

`reviews/models.py`:

```python
from django.conf import settings
from django.db import models

from architects.models import ArchitectProfile
from offers.models import Offer


class Review(models.Model):
    offer = models.OneToOneField(Offer, on_delete=models.CASCADE, related_name="review")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written")
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
```

Add `"reviews"` to `INSTALLED_APPS`.

Run: `python manage.py makemigrations reviews && python manage.py migrate && python manage.py test reviews.tests.test_models -v 2`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add reviews poydevor/settings.py
git commit -m "feat: Review model tied to completed offers"
```

- [ ] **Step 4: Write failing tests for review service (rating recompute)**

`reviews/tests/test_services.py`:

```python
from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from reviews.services import submit_review


class SubmitReviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")

    def _completed_offer(self):
        application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        return Offer.objects.create(
            application=application, architect=self.architect,
            source=Offer.Source.USER_INVITED, status=Offer.Status.COMPLETED,
        )

    def test_first_review_sets_rating_directly(self):
        offer = self._completed_offer()
        submit_review(offer, self.owner, rating=4, comment="Yaxshi")
        self.architect.refresh_from_db()
        self.assertEqual(self.architect.rating, 4)

    def test_second_review_averages_rating(self):
        offer1 = self._completed_offer()
        submit_review(offer1, self.owner, rating=4, comment="Yaxshi")
        offer2 = self._completed_offer()
        submit_review(offer2, self.owner, rating=2, comment="O'rtacha")
        self.architect.refresh_from_db()
        self.assertEqual(self.architect.rating, 3)
```

- [ ] **Step 5: Run to verify failure, implement service**

Run: `python manage.py test reviews.tests.test_services -v 2` — expect FAIL

`reviews/services.py`:

```python
from django.db import transaction
from django.db.models import Avg

from reviews.models import Review


@transaction.atomic
def submit_review(offer, user, rating: int, comment: str) -> Review:
    review = Review.objects.create(
        offer=offer, user=user, architect=offer.architect, rating=rating, comment=comment,
    )
    architect = offer.architect
    avg = architect.reviews.aggregate(avg=Avg("rating"))["avg"]
    architect.rating = round(avg, 2)
    architect.save(update_fields=["rating"])
    return review
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python manage.py test reviews.tests.test_services -v 2`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add reviews
git commit -m "feat: review submission recomputes architect's average rating"
```

- [ ] **Step 8: Write failing view test**

`reviews/tests/test_views.py`:

```python
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer


class SubmitReviewViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        self.offer = Offer.objects.create(
            application=application, architect=self.architect,
            source=Offer.Source.USER_INVITED, status=Offer.Status.COMPLETED,
        )
        self.client.force_login(self.owner)

    def test_submit_review(self):
        response = self.client.post(reverse("reviews:submit", args=[self.offer.pk]), {
            "rating": 5, "comment": "Zo'r ish!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(hasattr(self.offer, "review") or self.offer.review is not None)
```

- [ ] **Step 9: Run to verify failure, implement form/view/urls**

Run: `python manage.py test reviews.tests.test_views -v 2` — expect FAIL

`reviews/forms.py`:

```python
from django import forms


class ReviewForm(forms.Form):
    rating = forms.ChoiceField(choices=[(i, str(i)) for i in range(1, 6)], label="Baho")
    comment = forms.CharField(widget=forms.Textarea, required=False, label="Izoh")
```

`reviews/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from offers.models import Offer
from reviews.forms import ReviewForm
from reviews.services import submit_review


@login_required
def submit(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.COMPLETED,
    )
    if hasattr(offer, "review"):
        return redirect("applications:detail", pk=offer.application.pk)
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            submit_review(
                offer, request.user,
                rating=int(form.cleaned_data["rating"]), comment=form.cleaned_data["comment"],
            )
            return redirect("applications:detail", pk=offer.application.pk)
    else:
        form = ReviewForm()
    return render(request, "reviews/review_form.html", {"form": form, "offer": offer})
```

`reviews/urls.py`:

```python
from django.urls import path

from reviews import views

app_name = "reviews"
urlpatterns = [
    path("ariza/<int:offer_pk>/baholash/", views.submit, name="submit"),
]
```

Register in `poydevor/urls.py`.

- [ ] **Step 10: Wire template**

Update `templates/applications/detail.html`: for `completed` offers without a `review`, show "Baholash" link to `reviews:submit`; if reviewed, show the stored rating/comment instead.

Update `templates/architects/public_detail.html`: display `profile.reviews.all` (rating + comment + reviewer first name) below the portfolio section.

Create `templates/reviews/review_form.html`: star-rating radio buttons (1–5) + comment textarea + submit.

- [ ] **Step 11: Run tests to verify pass**

Run: `python manage.py test reviews -v 2`
Expected: PASS

- [ ] **Step 12: Register in admin, commit**

`reviews/admin.py`:

```python
from django.contrib import admin

from reviews.models import Review

admin.site.register(Review)
```

```bash
git add reviews templates poydevor
git commit -m "feat: review submission UI wired into application detail and architect profile"
```

---

## Chunk 7: seed data & final integration pass

**Files:**
- Create: `accounts/management/commands/seed_demo_data.py`
- Modify: `templates/architects/dashboard.html`, `templates/applications/dashboard.html` (final polish pass)
- Test: manual verification (see Step 4)

- [ ] **Step 1: Write the seed command**

`accounts/management/__init__.py`, `accounts/management/commands/__init__.py` (empty files), `accounts/management/commands/seed_demo_data.py`:

```python
from django.core.management.base import BaseCommand

from accounts.models import User
from architects.models import ArchitectProfile, Skill, Style
from wallet.models import Wallet
from wallet.services import topup_coins


class Command(BaseCommand):
    help = "Creates demo data: a few styles/skills and one architect account with 1000 coins."

    def handle(self, *args, **options):
        for name in ["Zamonaviy", "Klassik", "Minimalizm", "Loft"]:
            Style.objects.get_or_create(name=name)
        for name in ["3D vizualizatsiya", "Landshaft dizayni", "Interyer dizayni", "Qurilish nazorati"]:
            Skill.objects.get_or_create(name=name)

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
```

- [ ] **Step 2: Run the seed command**

Run: `python manage.py seed_demo_data`
Expected: "Demo arxitektor yaratildi: +998900000000 / demo12345 (1000 tanga)"

- [ ] **Step 3: Commit**

```bash
git add accounts/management
git commit -m "feat: seed_demo_data management command with 1000-coin demo architect"
```

- [ ] **Step 4: Full manual verification pass**

Run: `python manage.py runserver` and walk through, in a browser:
1. Sign up as a user → post an application (both known and "don't know size" paths) → browse architects → filter by style → open the demo architect's profile → send an application → confirm the "contacts visible after acceptance" notice appears.
2. Log in as the demo architect (`+998900000000` / `demo12345`) → accept the offer from step 1 → confirm the user's phone becomes visible in the architect dashboard, and the architect's phone/telegram become visible on the user's application detail page.
3. As the user, mark the offer complete → submit a review → confirm the architect's public profile shows the updated rating.
4. As the demo architect, browse open applications, use "Qatnashish" on one (confirm 20 coins deducted and it fails gracefully past 3 architects/insufficient coins), and buy more coins via the wallet dashboard.

Fix any bugs found directly (edit the relevant view/template, re-test that specific flow, commit the fix separately with a `fix:` message).

- [ ] **Step 5: Run the full test suite one last time**

Run: `python manage.py test -v 2`
Expected: PASS (all tests across all apps)

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: final integration fixes from manual verification pass"
```
