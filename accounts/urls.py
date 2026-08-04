from django.urls import path

from accounts import views

app_name = "accounts"
urlpatterns = [
    path("ro'yxatdan-o'tish/", views.signup, name="signup"),
    path("kirish/", views.login_view, name="login"),
    path("chiqish/", views.logout_view, name="logout"),
]
