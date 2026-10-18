from django.urls import path

from architects import views

app_name = "architects"
urlpatterns = [
    # Public
    path("arxitektorlar/", views.public_list, name="list"),
    path("loyihalar/", views.project_gallery, name="project_gallery"),
    path("loyihalar/<int:pk>/", views.project_detail, name="project_detail"),
    path("arxitektorlar/<int:pk>/", views.public_detail, name="detail"),
    # Registration
    path("architect/select-type/", views.select_type, name="select_type"),
    path("register/studio/", views.register_studio_view, name="register_studio"),
    path("register/employee/", views.register_employee_view, name="register_employee"),
    path("register/freelancer/", views.register_freelancer_view, name="register_freelancer"),
    path("register/status/", views.register_status, name="register_status"),
    # Architect area
    path("panel/", views.dashboard, name="dashboard"),
    path("studio/dashboard/", views.studio_dashboard, name="studio_dashboard"),
    path("studio/employees/<int:profile_id>/decision/", views.employee_decision, name="employee_decision"),
    path("studio/employees/<int:profile_id>/remove/", views.employee_remove, name="employee_remove"),
    path("studio/buyurtmalar/<int:assignment_id>/biriktirish/", views.assignment_assign, name="assignment_assign"),
    path("freelancer/dashboard/", views.freelancer_dashboard, name="freelancer_dashboard"),
    path("employee/workspace/", views.employee_workspace, name="employee_workspace"),
    path("employee/buyurtmalar/<int:assignment_id>/olish/", views.assignment_claim, name="assignment_claim"),
    path("employee/buyurtmalar/<int:assignment_id>/bajarildi/", views.assignment_done, name="assignment_done"),
    path("panel/portfolio/", views.portfolio, name="portfolio"),
    path("panel/profil/", views.portfolio_edit, name="portfolio_edit"),
    path("panel/loyiha/qo'shish/", views.project_create, name="project_create"),
    path("panel/loyiha/<int:project_id>/", views.my_project, name="my_project"),
    path("panel/loyiha/<int:project_id>/tahrirlash/", views.project_edit, name="project_edit"),
    path("panel/loyiha/<int:project_id>/ochirish/", views.project_delete, name="project_delete"),
    path("panel/loyiha/<int:project_id>/rasm/<int:image_id>/ochirish/", views.project_photo_delete, name="project_photo_delete"),
    path("panel/loyiha/<int:project_id>/rasm-qo'shish/", views.project_image_add, name="project_image_add"),
]
