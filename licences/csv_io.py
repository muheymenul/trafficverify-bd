from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.csv_tools import (
    CsvImportError,
    flatten_validation_error,
    get_choice,
    get_date,
    get_text,
    read_rows,
)

from .models import Driver, DrivingLicence

EXPORT_COLUMNS = [
    "licence_number",
    "driver_name",
    "date_of_birth",
    "licence_class",
    "issue_date",
    "expiry_date",
    "status",
]
REQUIRED = (
    "licence_number",
    "driver_name",
    "date_of_birth",
    "licence_class",
    "issue_date",
    "expiry_date",
)
OPTIONAL = ("status",)
DEMO_PREFIX = "DEMO-"


def licence_export_row(lic):
    return [
        lic.licence_number,
        lic.driver.full_name,
        lic.driver.date_of_birth,
        lic.licence_class,
        lic.issue_date,
        lic.expiry_date,
        lic.status,
    ]


def import_licences(upload):
    """Returns (created, updated). Raises CsvImportError; saves nothing then."""
    rows = read_rows(upload, REQUIRED, OPTIONAL)
    today = timezone.localdate()

    errors, to_save, seen = [], [], set()

    for line_no, row in rows:
        errs = []

        number = get_text(row, "licence_number", errs).upper()
        if number:
            if not number.startswith(DEMO_PREFIX):
                errs.append(f"'licence_number' must start with {DEMO_PREFIX} (demo data only).")
            if number in seen:
                errs.append("This licence number appears twice in the file.")
            seen.add(number)

        name = get_text(row, "driver_name", errs)
        birth = get_date(row, "date_of_birth", errs)
        if birth and (birth >= today or birth.year < 1900):
            errs.append("'date_of_birth' must be a past date after 1900.")
        licence_class = get_choice(row, "licence_class", DrivingLicence.LicenceClass.values, errs)
        issue = get_date(row, "issue_date", errs)
        expiry = get_date(row, "expiry_date", errs)
        status = get_choice(row, "status", DrivingLicence.Status.values, errs, default="ACTIVE")

        if not errs:
            existing = (
                DrivingLicence.objects.select_related("driver")
                .filter(licence_number=number)
                .first()
            )
            driver = existing.driver if existing else Driver()
            driver.full_name = name
            driver.date_of_birth = birth

            licence = existing or DrivingLicence()
            licence.licence_number = number
            licence.licence_class = licence_class
            licence.issue_date = issue
            licence.expiry_date = expiry
            licence.status = status

            try:
                driver.full_clean(exclude=["photo"])
            except ValidationError as exc:
                errs.extend(flatten_validation_error(exc))
            try:
                licence.full_clean(exclude=["driver"])
            except ValidationError as exc:
                errs.extend(flatten_validation_error(exc))

            if not errs:
                to_save.append((driver, licence, existing is None))

        errors.extend(f"Row {line_no}: {e}" for e in errs)

    if errors:
        raise CsvImportError(errors)

    with transaction.atomic():
        for driver, licence, _ in to_save:
            driver.save()
            licence.driver = driver
            licence.save()

    created = sum(1 for _, _, is_new in to_save if is_new)
    return created, len(to_save) - created