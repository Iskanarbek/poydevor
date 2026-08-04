from django.urls import path

from applications import views

app_name = "applications"
urlpatterns = [
    path("elon/joylashtirish/", views.post_application, name="post"),
    path("panel/elonlarim/", views.dashboard, name="dashboard"),
    path("elon/<int:pk>/", views.detail, name="detail"),
]
