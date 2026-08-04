from django.urls import path

from offers import views

app_name = "offers"
urlpatterns = [
    path("arxitektor/<int:architect_pk>/ariza-yuborish/", views.send_from_architect_profile, name="send"),
    path("elon/<int:application_pk>/qatnashish/", views.architect_apply, name="architect_apply"),
    path("ariza/<int:offer_pk>/javob/", views.respond, name="respond"),
    path("ariza/<int:offer_pk>/foydalanuvchi-javob/", views.user_respond, name="user_respond"),
    path("ariza/<int:offer_pk>/yakunlash/", views.mark_complete, name="complete"),
]
