from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from notifications.models import Notification


@login_required
def notification_list(request):
    notifications = list(request.user.notifications.all()[:100])
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
def notification_open(request, pk):
    """Mark one notification read and go where it points."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    target = notification.url
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("notifications:list")


@login_required
def mark_all_read(request):
    if request.method == "POST":
        request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("notifications:list")
