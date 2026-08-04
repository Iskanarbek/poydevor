from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from offers.models import Offer
from reviews.forms import ReviewForm
from reviews.services import submit_review


@login_required
def submit(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.COMPLETED,
    )
    if hasattr(offer, "review"):
        return redirect("applications:detail", pk=offer.application.pk)
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            submit_review(
                offer, request.user,
                rating=int(form.cleaned_data["rating"]), comment=form.cleaned_data["comment"],
            )
            return redirect("applications:detail", pk=offer.application.pk)
    else:
        form = ReviewForm()
    return render(request, "reviews/review_form.html", {"form": form, "offer": offer})
