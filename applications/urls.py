from django.urls import path

from applications import views

app_name = "applications"
urlpatterns = [
    path("elon/joylashtirish/", views.post_application, name="post"),
    path("elon/narx/", views.price_estimate, name="price_estimate"),
    path("panel/elonlarim/", views.dashboard, name="dashboard"),
    path("elon/<int:pk>/", views.detail, name="detail"),
    path("elon/<int:pk>/ochirish/", views.delete_application, name="delete"),
]
