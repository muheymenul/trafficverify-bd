from django.contrib import admin
from django.utils import timezone

from accounts.csv_tools import CsvImportAdminMixin, csv_response

from .csv_io import EXPORT_COLUMNS, import_vehicles, vehicle_export_row
from .models import Vehicle


def _expiry_label(expiry_date):
    """Return a simple text label for a date (used only for the admin list)."""
    if expiry_date is None:
        return "Not set"
    if expiry_date < timezone.localdate():
        return "Expired"
    return "Valid"


@admin.register(Vehicle)
class VehicleAdmin(CsvImportAdminMixin, admin.ModelAdmin):
    list_display = (
        "registration_number",
        "vehicle_type",
        "owner_name",
        "registration_status",
        "record_status",
        "tax_token_check",
        "fitness_check",
        "insurance_check",
    )
    list_filter = ("vehicle_type", "registration_status", "record_status")
    search_fields = ("registration_number", "owner_name")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 25
    actions = ["export_csv"]

    # --- CSV import settings (used by CsvImportAdminMixin) ---
    csv_importer = staticmethod(import_vehicles)  # staticmethod: not bound to self
    csv_import_title = "Import vehicles from CSV"
    csv_import_columns = (
        ("registration_number", True, "Must start with DEMO- (letters, numbers, hyphens, 5-20 characters)."),
        ("vehicle_type", True, "MOTORCYCLE, CAR, BUS, TRUCK, PICKUP, CNG or OTHER."),
        ("owner_name", True, "Fictional owner name."),
        ("registration_status", False, "ACTIVE, SUSPENDED or CANCELLED. Empty = ACTIVE."),
        ("tax_token_expiry", False, "Date as YYYY-MM-DD, or empty."),
        ("fitness_expiry", False, "Date as YYYY-MM-DD, or empty."),
        ("insurance_expiry", False, "Date as YYYY-MM-DD, or empty."),
        ("record_status", False, "ACTIVE or INACTIVE. Empty = ACTIVE."),
    )
    csv_import_notes = (
        "A row with an existing registration number REPLACES that record. Empty date cells clear the date.",
        "Maximum 500 rows per file.",
    )

    @admin.action(description="Export selected vehicles to CSV")
    def export_csv(self, request, queryset):
        rows = (vehicle_export_row(v) for v in queryset.order_by("registration_number"))
        return csv_response("vehicles_demo.csv", EXPORT_COLUMNS, rows)

    @admin.display(description="Tax token")
    def tax_token_check(self, obj):
        return _expiry_label(obj.tax_token_expiry)

    @admin.display(description="Fitness")
    def fitness_check(self, obj):
        return _expiry_label(obj.fitness_expiry)

    @admin.display(description="Insurance")
    def insurance_check(self, obj):
        return _expiry_label(obj.insurance_expiry)