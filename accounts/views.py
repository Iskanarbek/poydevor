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
