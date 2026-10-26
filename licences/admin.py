from django.contrib import admin
from django.utils import timezone

from accounts.csv_tools import CsvImportAdminMixin, csv_response

from .csv_io import EXPORT_COLUMNS, import_licences, licence_export_row
from .models import Driver, DrivingLicence


class DrivingLicenceInline(admin.TabularInline):
    """Shows a driver's licences inside the driver page."""

    model = DrivingLicence
    extra = 0
    fields = ("licence_number", "licence_class", "issue_date", "expiry_date", "status")


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("full_name", "date_of_birth", "licence_count", "created_at")
    search_fields = ("full_name", "licences__licence_number")
    readonly_fields = ("created_at",)
    inlines = [DrivingLicenceInline]
    list_per_page = 25

    @admin.display(description="Licences")
    def licence_count(self, obj):
        return obj.licences.count()


@admin.register(DrivingLicence)
class DrivingLicenceAdmin(CsvImportAdminMixin, admin.ModelAdmin):
    list_display = (
        "licence_number",
        "driver",
        "licence_class",
        "issue_date",
        "expiry_date",
        "status",
        "expiry_check",
    )
    list_filter = ("licence_class", "status")
    search_fields = ("licence_number", "driver__full_name")
    list_select_related = ("driver",)
    autocomplete_fields = ("driver",)
    date_hierarchy = "expiry_date"
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 25
    actions = ["export_csv"]

    # --- CSV import settings (used by CsvImportAdminMixin) ---
    csv_importer = staticmethod(import_licences)  # staticmethod: not bound to self
    csv_import_title = "Import driving licences from CSV"
    csv_import_columns = (
        ("licence_number", True, "Must start with DEMO- (letters, numbers, hyphens, 5-20 characters)."),
        ("driver_name", True, "Fictional driver name."),
        ("date_of_birth", True, "Fictional date as YYYY-MM-DD (must be in the past)."),
        ("licence_class", True, "MOTORCYCLE, LIGHT, MEDIUM, HEAVY or PROFESSIONAL."),
        ("issue_date", True, "Date as YYYY-MM-DD."),
        ("expiry_date", True, "Date as YYYY-MM-DD, after the issue date."),
        ("status", False, "ACTIVE, SUSPENDED or REVOKED. Empty = ACTIVE."),
    )
    csv_import_notes = (
        "A new licence number creates a new driver. An existing licence number updates that licence and its driver's name and date of birth.",
        "Driver photos can not be imported by CSV. Add them in the driver page.",
        "Maximum 500 rows per file.",
    )

    @admin.action(description="Export selected licences to CSV")
    def export_csv(self, request, queryset):
        rows = (
            licence_export_row(lic)
            for lic in queryset.select_related("driver").order_by("licence_number")
        )
        return csv_response("licences_demo.csv", EXPORT_COLUMNS, rows)

    @admin.display(description="Expiry check")
    def expiry_check(self, obj):
        if obj.expiry_date < timezone.localdate():
            return "Expired"
        return "Not expired"