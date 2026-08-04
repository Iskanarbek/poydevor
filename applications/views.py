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
