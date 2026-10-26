from django.contrib import admin

from .models import VerificationLog


@admin.register(VerificationLog)
class VerificationLogAdmin(admin.ModelAdmin):
    """Read-only: no one can add, edit or delete audit logs here."""

    list_display = (
        "created_at",
        "officer",
        "police_id",
        "officer_rank",
        "verification_type",
        "searched_identifier",
        "result_category",
    )
    list_filter = ("verification_type", "result_category", "created_at")
    search_fields = (
        "officer__username",
        "officer__police_profile__demo_police_id",
        "searched_identifier",
    )
    list_select_related = ("officer", "officer__police_profile")
    date_hierarchy = "created_at"
    list_per_page = 50

    @admin.display(description="Demo Police ID")
    def police_id(self, obj):
        profile = getattr(obj.officer, "police_profile", None)
        return profile.demo_police_id if profile else "-"

    @admin.display(description="Rank")
    def officer_rank(self, obj):
        profile = getattr(obj.officer, "police_profile", None)
        return profile.get_rank_display() if profile else "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False