from django.contrib import admin

from offers.models import Offer, StudioAssignment

admin.site.register(Offer)


@admin.register(StudioAssignment)
class StudioAssignmentAdmin(admin.ModelAdmin):
    list_display = ["offer", "worker", "status", "deadline", "assigned_at", "done_at"]
    list_filter = ["status"]
    search_fields = ["offer__application__location", "worker__user__first_name", "worker__user__last_name"]
