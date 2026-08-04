from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from reviews.models import Review


class ReviewModelTests(TestCase):
    def test_create_review_tied_to_completed_offer(self):
        owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        application = Application.objects.create(owner=owner, rooms_count=3, location="Toshkent")
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        architect = ArchitectProfile.objects.create(user=architect_user, bio="x")
        offer = Offer.objects.create(
            application=application, architect=architect,
            source=Offer.Source.USER_INVITED, status=Offer.Status.COMPLETED,
        )
        review = Review.objects.create(offer=offer, user=owner, architect=architect, rating=5, comment="Ajoyib!")
        self.assertEqual(review.rating, 5)
