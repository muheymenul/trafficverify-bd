from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.csv_tools import (
    CsvImportError,
    flatten_validation_error,
    get_choice,
    get_date,
    get_text,
    read_rows,
)

from .models import Vehicle

EXPORT_COLUMNS = [
    "registration_number",
    "vehicle_type",
    "owner_name",
    "registration_status",
    "tax_token_expiry",
    "fitness_expiry",
    "insurance_expiry",
    "record_status",
]
REQUIRED = ("registration_number", "vehicle_type", "owner_name")
OPTIONAL = (
    "registration_status",
    "tax_token_expiry",
    "fitness_expiry",
    "insurance_expiry",
    "record_status",
)
DEMO_PREFIX = "DEMO-"


def vehicle_export_row(v):
    return [
        v.registration_number,
        v.vehicle_type,
        v.owner_name,
        v.registration_status,
        v.tax_token_expiry or "",
        v.fitness_expiry or "",
        v.insurance_expiry or "",
        v.record_status,
    ]


def import_vehicles(upload):
    """Returns (created, updated). Raises CsvImportError; saves nothing then."""
    rows = read_rows(upload, REQUIRED, OPTIONAL)

    errors, to_save, seen = [], [], set()

    for line_no, row in rows:
        errs = []

        number = get_text(row, "registration_number", errs).upper()
        if number:
            if not number.startswith(DEMO_PREFIX):
                errs.append(f"'registration_number' must start with {DEMO_PREFIX} (demo data only).")
            if number in seen:
                errs.append("This registration number appears twice in the file.")
            seen.add(number)

        vehicle_type = get_choice(row, "vehicle_type", Vehicle.VehicleType.values, errs)
        owner = get_text(row, "owner_name", errs)
        reg_status = get_choice(
            row, "registration_status", Vehicle.RegistrationStatus.values, errs, default="ACTIVE"
        )
        record_status = get_choice(
            row, "record_status", Vehicle.RecordStatus.values, errs, default="ACTIVE"
        )
        tax = get_date(row, "tax_token_expiry", errs, required=False)
        fitness = get_date(row, "fitness_expiry", errs, required=False)
        insurance = get_date(row, "insurance_expiry", errs, required=False)

        if not errs:
            existing = Vehicle.objects.filter(registration_number=number).first()
            vehicle = existing or Vehicle()
            vehicle.registration_number = number
            vehicle.vehicle_type = vehicle_type
            vehicle.owner_name = owner
            vehicle.registration_status = reg_status
            vehicle.record_status = record_status
            vehicle.tax_token_expiry = tax
            vehicle.fitness_expiry = fitness
            vehicle.insurance_expiry = insurance
            try:
                vehicle.full_clean()
            except ValidationError as exc:
                errs.extend(flatten_validation_error(exc))
            else:
                to_save.append((vehicle, existing is None))

        errors.extend(f"Row {line_no}: {e}" for e in errs)

    if errors:
        raise CsvImportError(errors)

    with transaction.atomic():
        for vehicle, _ in to_save:
            vehicle.save()

    created = sum(1 for _, is_new in to_save if is_new)
    return created, len(to_save) - created