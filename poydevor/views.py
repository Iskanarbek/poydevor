from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def dashboard_redirect(request):
    if request.user.role == request.user.Role.ARCHITECT:
        return redirect("architects:dashboard")
    return redirect("applications:dashboard")
