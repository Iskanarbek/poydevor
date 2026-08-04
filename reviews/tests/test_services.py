from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from reviews.services import submit_review


class SubmitReviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone="+998901111111", password="x", first_name="Aziz", last_name="K", role=User.Role.USER,
        )
        architect_user = User.objects.create_user(
            phone="+998902222222", password="x", first_name="Nodir", last_name="Y", role=User.Role.ARCHITECT,
        )
        self.architect = ArchitectProfile.objects.create(user=architect_user, bio="x")

    def _completed_offer(self):
        application = Application.objects.create(owner=self.owner, rooms_count=3, location="Toshkent")
        return Offer.objects.create(
            application=application, architect=self.architect,
            source=Offer.Source.USER_INVITED, status=Offer.Status.COMPLETED,
        )

    def test_first_review_sets_rating_directly(self):
        offer = self._completed_offer()
        submit_review(offer, self.owner, rating=4, comment="Yaxshi")
        self.architect.refresh_from_db()
        self.assertEqual(self.architect.rating, 4)

    def test_second_review_averages_rating(self):
        offer1 = self._completed_offer()
        submit_review(offer1, self.owner, rating=4, comment="Yaxshi")
        offer2 = self._completed_offer()
        submit_review(offer2, self.owner, rating=2, comment="O'rtacha")
        self.architect.refresh_from_db()
        self.assertEqual(self.architect.rating, 3)

    def test_submit_review_locks_architect_row_before_recomputing_rating(self):
        """Guards against the lost-update race: two near-simultaneous submissions for
        different offers of the same architect must serialize on the ArchitectProfile
        row (via select_for_update) before recomputing the average, so neither
        transaction's aggregate misses the other's just-inserted review."""
        offer1 = self._completed_offer()
        offer2 = self._completed_offer()

        with patch(
            "reviews.services.ArchitectProfile.objects.select_for_update",
            wraps=ArchitectProfile.objects.select_for_update,
        ) as mock_select_for_update:
            submit_review(offer1, self.owner, rating=4, comment="Yaxshi")
            submit_review(offer2, self.owner, rating=2, comment="O'rtacha")

        self.assertEqual(mock_select_for_update.call_count, 2)
        self.architect.refresh_from_db()
        self.assertEqual(self.architect.rating, 3)
