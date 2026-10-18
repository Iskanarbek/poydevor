from django.contrib.auth import login as auth_login, logout as auth_logout
from django.shortcuts import redirect, render

from accounts.forms import LoginForm, SignupForm

PHONE_BACKEND = "accounts.backends.PhoneBackend"


def login_without_password(request, user):
    """Log ``user`` in right after they registered (no password exists)."""
    auth_login(request, user, backend=PHONE_BACKEND)


def welcome(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "accounts/welcome.html")


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            login_without_password(request, form.save())
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
    """Ask first: only a confirmed POST signs the visitor out, so a stray link
    or a page pre-fetch can never log anyone out by accident."""
    if not request.user.is_authenticated:
        return redirect("accounts:welcome")
    if request.method == "POST":
        auth_logout(request)
        return redirect("accounts:welcome")
    return render(request, "accounts/logout_confirm.html")
