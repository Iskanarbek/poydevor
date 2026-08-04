from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from reviews.models import Review


class SubmitReviewViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        self.offer = Offer.objects.create(
            application=application, architect=self.architect,
            source=Offer.Source.USER_INVITED, status=Offer.Status.COMPLETED,
        )
        self.client.force_login(self.owner)

    def test_submit_review(self):
        response = self.client.post(reverse("reviews:submit", args=[self.offer.pk]), {
            "rating": 5, "comment": "Zo'r ish!",
        })
        self.assertEqual(response.status_code, 302)
        review = Review.objects.get(offer=self.offer)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Zo'r ish!")
        self.assertEqual(review.architect, self.architect)
