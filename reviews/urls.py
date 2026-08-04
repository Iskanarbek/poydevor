from django.urls import path

from reviews import views

app_name = "reviews"
urlpatterns = [
    path("ariza/<int:offer_pk>/baholash/", views.submit, name="submit"),
]
