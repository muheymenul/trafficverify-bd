from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashWidget, UserChangeForm

from .csv_io import EXPORT_COLUMNS, import_police, police_export_row
from .csv_tools import CsvImportAdminMixin, csv_response
from .models import PoliceRecord, User


# ---------------------------------------------------------------
# Hide the hash details (algorithm, salt, hash) on the user page
# ---------------------------------------------------------------
class HiddenHashWidget(ReadOnlyPasswordHashWidget):
    """Shows a simple message instead of the hash summary."""

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["summary"] = [
            {"label": "Password is stored securely (hashed) and cannot be viewed."}
        ]
        return context


class OfficerUserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "password" in self.fields:
            self.fields["password"].widget = HiddenHashWidget()


# ---------------------------------------------------------------
# User accounts (officers and administrators)
# ---------------------------------------------------------------
@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = OfficerUserChangeForm
    list_display = ("username", "email", "role", "is_active", "is_staff", "last_login")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
    list_per_page = 25

    # Add the "role" field to the edit page and the "add user" page.
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("TrafficVerify role", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("TrafficVerify role", {"fields": ("role",)}),
    )

    def save_model(self, request, obj, form, change):
        """
        Server-side rule (not just hidden buttons):
        - Administrators may enter the admin panel (is_staff = True).
        - Police officers can NEVER be staff or superuser.
        """
        if obj.is_superuser or obj.role == User.Role.ADMINISTRATOR:
            obj.role = User.Role.ADMINISTRATOR
            obj.is_staff = True
        else:
            obj.role = User.Role.OFFICER
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------
# Fictional police records
# ---------------------------------------------------------------
class PoliceRecordAdminForm(forms.ModelForm):
    """
    Adds a write-only box for the registration code.
    The code is hashed before saving, so nobody can read it later.
    """

    new_registration_code = forms.CharField(
        label="Set / change registration code",
        required=False,
        min_length=8,
        max_length=64,
        widget=forms.PasswordInput(render_value=False),
        help_text=(
            "Minimum 8 characters. It is stored hashed and can NOT be viewed "
            "later. Leave empty to keep the current code."
        ),
    )

    class Meta:
        model = PoliceRecord
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        is_new = self.instance.pk is None
        if is_new and not cleaned.get("new_registration_code"):
            self.add_error(
                "new_registration_code",
                "A registration code is required for a new police record.",
            )
        return cleaned


@admin.register(PoliceRecord)
class PoliceRecordAdmin(CsvImportAdminMixin, admin.ModelAdmin):
    form = PoliceRecordAdminForm
    list_display = (
        "demo_police_id",
        "full_name",
        "rank",
        "unit",
        "is_eligible",
        "claim_status",
    )
    list_filter = ("rank", "unit", "is_eligible")
    search_fields = ("demo_police_id", "full_name", "unit")
    readonly_fields = ("claimed_by", "claimed_at", "created_at")
    list_per_page = 25
    actions = ["disable_records", "enable_records", "export_csv"]

    # --- CSV import settings (used by CsvImportAdminMixin) ---
    csv_importer = staticmethod(import_police)  # staticmethod: not bound to self
    csv_import_title = "Import police records from CSV"
    csv_import_columns = (
        ("demo_police_id", True, "Must start with DEMO-P- (fictional ID)."),
        ("full_name", True, "Fictional name."),
        ("rank", True, "CONSTABLE, NAIK, ASI, SI, INSPECTOR or ASP."),
        ("unit", True, "Fictional unit name."),
        ("is_eligible", False, "true or false. Empty = true for new records, unchanged for existing ones."),
        ("registration_code", False, "8-64 characters. REQUIRED for new records. Empty keeps the old code of an existing record."),
    )
    csv_import_notes = (
        "Registration codes are hashed when saved. Delete your CSV file after importing, because it contains plain codes.",
        "Exported files never contain registration codes.",
        "Maximum 100 rows per file (hashing codes is slow on purpose). Large files may take a minute.",
    )

    @admin.display(description="Claimed?", boolean=True)
    def claim_status(self, obj):
        return obj.is_claimed

    def save_model(self, request, obj, form, change):
        code = form.cleaned_data.get("new_registration_code")
        if code:
            obj.set_registration_code(code)
        super().save_model(request, obj, form, change)

    @admin.action(description="Disable selected records (cannot register)")
    def disable_records(self, request, queryset):
        count = queryset.update(is_eligible=False)
        self.message_user(request, f"{count} record(s) disabled.", messages.SUCCESS)

    @admin.action(description="Enable selected records")
    def enable_records(self, request, queryset):
        count = queryset.update(is_eligible=True)
        self.message_user(request, f"{count} record(s) enabled.", messages.SUCCESS)

    @admin.action(description="Export selected police records to CSV (no codes)")
    def export_csv(self, request, queryset):
        rows = (police_export_row(r) for r in queryset.order_by("demo_police_id"))
        return csv_response("police_records_demo.csv", EXPORT_COLUMNS, rows)