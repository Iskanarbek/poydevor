from django.urls import path

from architects import views

app_name = "architects"
urlpatterns = [
    path("arxitektorlar/", views.public_list, name="list"),
    path("loyihalar/", views.project_gallery, name="project_gallery"),
    path("arxitektorlar/<int:pk>/", views.public_detail, name="detail"),
    path("panel/ro'yxatdan-o'tish/", views.onboarding, name="onboarding"),
    path("panel/", views.dashboard, name="dashboard"),
    path("panel/profil/", views.portfolio_edit, name="portfolio_edit"),
    path("panel/loyiha/qo'shish/", views.project_create, name="project_create"),
    path("panel/loyiha/<int:project_id>/rasm-qo'shish/", views.project_image_add, name="project_image_add"),
]
