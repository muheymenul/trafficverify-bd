"""
Shared tools for CSV import / export in the Django Admin (DEMO data only).

Safety rules:
- Import is all-or-nothing: every row is checked first, and nothing is saved
  if even one row has a problem.
- Cells that start with = + - @ are rejected on import and escaped on export
  (protects against spreadsheet formula injection).
"""

import csv
import io
from datetime import date

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

MAX_FILE_BYTES = 1_000_000
DEFAULT_MAX_ROWS = 500
MAX_ERRORS_SHOWN = 40
DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r")


class CsvImportError(Exception):
    """Raised when a CSV file can not be imported. Nothing was saved."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("CSV import failed")


# ---------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------
def safe_cell(value):
    """Make a value safe to open in Excel (no formula can start)."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in DANGEROUS_START:
        return "'" + text
    return text


def csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # BOM, so Excel reads the file as UTF-8
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return response


# ---------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------
def read_rows(upload, required, optional=(), max_rows=DEFAULT_MAX_ROWS):
    """
    Read an uploaded CSV file.
    Returns a list of (line_number, {column: text}).
    Raises CsvImportError for problems with the file itself.
    """
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvImportError(
            ["The file is not UTF-8 text. In Excel, save it as 'CSV UTF-8'."]
        )
    if "\x00" in text:
        raise CsvImportError(["The file contains invalid characters."])

    try:
        all_rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise CsvImportError([f"The file is not a valid CSV: {exc}"])

    if not all_rows:
        raise CsvImportError(["The file is empty."])

    header = [h.strip().lower() for h in all_rows[0]]
    allowed = list(required) + list(optional)
    problems = []

    missing = [c for c in required if c not in header]
    if missing:
        problems.append("Missing column(s): " + ", ".join(missing))
    unknown = [h or "(empty name)" for h in header if h not in allowed]
    if unknown:
        problems.append("Unknown column(s): " + ", ".join(unknown))
    if len(set(header)) != len(header):
        problems.append("The header has a repeated column name.")
    if problems:
        raise CsvImportError(problems)

    rows = []
    for line_no, values in enumerate(all_rows[1:], start=2):
        if not any(v.strip() for v in values):
            continue  # skip blank lines
        if len(values) > len(header):
            problems.append(f"Row {line_no}: more values than columns.")
            continue
        values = values + [""] * (len(header) - len(values))
        rows.append((line_no, {h: v.strip() for h, v in zip(header, values)}))
        if len(rows) > max_rows:
            raise CsvImportError([f"Too many rows. The limit is {max_rows} rows per file."])

    if problems:
        raise CsvImportError(problems)
    if not rows:
        raise CsvImportError(["The file has a header but no data rows."])
    return rows


def get_text(row, key, errs, required=True):
    value = row.get(key, "")
    if not value:
        if required:
            errs.append(f"'{key}' is required.")
        return ""
    if value[0] in DANGEROUS_START:
        errs.append(f"'{key}' must not start with = + - or @ (spreadsheet formula risk).")
    return value


def get_date(row, key, errs, required=True):
    value = row.get(key, "")
    if not value:
        if required:
            errs.append(f"'{key}' is required.")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errs.append(f"'{key}' must be a date like 2028-12-31 (year-month-day).")
        return None


def get_choice(row, key, allowed, errs, default=None):
    value = row.get(key, "").upper()
    if not value:
        if default is not None:
            return default
        errs.append(f"'{key}' is required.")
        return ""
    if value not in allowed:
        errs.append(f"'{key}' must be one of: {', '.join(allowed)}.")
        return ""
    return value


def get_bool(row, key, errs):
    """True / False, or None when the cell is empty."""
    value = row.get(key, "").lower()
    if value == "":
        return None
    if value in ("true", "yes", "1"):
        return True
    if value in ("false", "no", "0"):
        return False
    errs.append(f"'{key}' must be true or false.")
    return None


def flatten_validation_error(exc):
    if hasattr(exc, "message_dict"):
        return [f"{field}: {msg}" for field, msgs in exc.message_dict.items() for msg in msgs]
    return list(exc.messages)


# ---------------------------------------------------------------
# Admin pieces
# ---------------------------------------------------------------
class CsvUploadForm(forms.Form):
    file = forms.FileField(label="CSV file (.csv, UTF-8, max 1 MB)")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        if upload.size > MAX_FILE_BYTES:
            raise forms.ValidationError("The file is larger than 1 MB.")
        return upload


class CsvImportAdminMixin:
    """
    Adds an 'Import CSV' button and page to a ModelAdmin.

    The admin class must define:
      csv_importer       = staticmethod(function)   # function(upload) -> (created, updated)
      csv_import_title   = "Import ... from CSV"
      csv_import_columns = [(name, required_bool, help_text), ...]
      csv_import_notes   = ["...", ...]
    """

    change_list_template = "admin/csv_change_list.html"
    csv_import_title = "Import from CSV"
    csv_import_columns = ()
    csv_import_notes = ()

    def _info(self):
        return self.model._meta.app_label, self.model._meta.model_name

    def _can_import(self, request):
        return self.has_add_permission(request) and self.has_change_permission(request)

    def get_urls(self):
        app, model = self._info()
        custom = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name=f"{app}_{model}_import_csv",
            )
        ]
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self._can_import(request):
            app, model = self._info()
            extra_context["csv_import_url"] = reverse(f"admin:{app}_{model}_import_csv")
        return super().changelist_view(request, extra_context=extra_context)

    def import_csv_view(self, request):
        # Checked on the server: only users who may add AND change records.
        if not self._can_import(request):
            raise PermissionDenied

        app, model = self._info()
        errors = []

        if request.method == "POST":
            form = CsvUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    created, updated = self.csv_importer(form.cleaned_data["file"])
                except CsvImportError as exc:
                    errors = exc.errors
                except DatabaseError:
                    errors = ["The database rejected the data. Nothing was imported."]
                else:
                    self.message_user(
                        request,
                        f"Import finished: {created} created, {updated} updated.",
                        messages.SUCCESS,
                    )
                    return redirect(f"admin:{app}_{model}_changelist")
        else:
            form = CsvUploadForm()

        if len(errors) > MAX_ERRORS_SHOWN:
            extra = len(errors) - MAX_ERRORS_SHOWN
            errors = errors[:MAX_ERRORS_SHOWN] + [f"... and {extra} more problem(s)."]

        context = {
            **self.admin_site.each_context(request),
            "title": self.csv_import_title,
            "opts": self.model._meta,
            "form": form,
            "errors": errors,
            "columns": self.csv_import_columns,
            "notes": self.csv_import_notes,
            "changelist_url": reverse(f"admin:{app}_{model}_changelist"),
        }
        return TemplateResponse(request, "admin/csv_import.html", context)