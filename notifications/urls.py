from django.urls import path

from notifications import views

app_name = "notifications"
urlpatterns = [
    path("bildirishnomalar/", views.notification_list, name="list"),
    path("bildirishnomalar/hammasi-oqildi/", views.mark_all_read, name="mark_all_read"),
    path("bildirishnomalar/<int:pk>/", views.notification_open, name="open"),
]
