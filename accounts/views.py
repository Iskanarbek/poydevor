from django.contrib.auth import login as auth_login, logout as auth_logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

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


def _next_url(request):
    """The page a visitor was heading to before being sent to the login screen, if it is
    one of ours (never an outside address)."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return ""


def login_view(request):
    next_url = _next_url(request)
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            auth_login(request, form.cleaned_data["user"])
            return redirect(next_url or "dashboard")
    else:
        if request.user.is_authenticated:
            return redirect(next_url or "dashboard")
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def logout_view(request):
    """Ask first: only a confirmed POST signs the visitor out, so a stray link
    or a page pre-fetch can never log anyone out by accident."""
    if not request.user.is_authenticated:
        return redirect("accounts:welcome")
    if request.method == "POST":
        auth_logout(request)
        return redirect("accounts:welcome")
    return render(request, "accounts/logout_confirm.html")
