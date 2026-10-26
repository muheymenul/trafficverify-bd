from django.core.exceptions import ValidationError
from django.db import transaction

from .csv_tools import (
    CsvImportError,
    flatten_validation_error,
    get_bool,
    get_choice,
    get_text,
    read_rows,
)
from .models import PoliceRecord

# NOTE: the registration code is never exported (only a hash is stored).
EXPORT_COLUMNS = ["demo_police_id", "full_name", "rank", "unit", "is_eligible"]
REQUIRED = ("demo_police_id", "full_name", "rank", "unit")
OPTIONAL = ("is_eligible", "registration_code")
DEMO_PREFIX = "DEMO-P-"
MAX_ROWS = 100  # hashing every registration code is slow on purpose


def police_export_row(r):
    return [r.demo_police_id, r.full_name, r.rank, r.unit, r.is_eligible]


def import_police(upload):
    """Returns (created, updated). Raises CsvImportError; saves nothing then."""
    rows = read_rows(upload, REQUIRED, OPTIONAL, max_rows=MAX_ROWS)

    errors, to_save, seen = [], [], set()

    for line_no, row in rows:
        errs = []

        police_id = get_text(row, "demo_police_id", errs).upper()
        if police_id:
            if not police_id.startswith(DEMO_PREFIX):
                errs.append(f"'demo_police_id' must start with {DEMO_PREFIX} (demo data only).")
            if police_id in seen:
                errs.append("This Demo Police ID appears twice in the file.")
            seen.add(police_id)

        name = get_text(row, "full_name", errs)
        rank = get_choice(row, "rank", PoliceRecord.Rank.values, errs)
        unit = get_text(row, "unit", errs)
        eligible = get_bool(row, "is_eligible", errs)
        code = row.get("registration_code", "")  # secret: not echoed anywhere

        if code and not (8 <= len(code) <= 64):
            errs.append("'registration_code' must be 8 to 64 characters.")

        if not errs:
            existing = PoliceRecord.objects.filter(demo_police_id=police_id).first()
            if existing is None and not code:
                errs.append("'registration_code' is required for a new record.")
            else:
                record = existing or PoliceRecord()
                record.demo_police_id = police_id
                record.full_name = name
                record.rank = rank
                record.unit = unit
                if eligible is not None:
                    record.is_eligible = eligible
                try:
                    record.full_clean()
                except ValidationError as exc:
                    errs.extend(flatten_validation_error(exc))
                else:
                    to_save.append((record, existing is None, code))

        errors.extend(f"Row {line_no}: {e}" for e in errs)

    if errors:
        raise CsvImportError(errors)

    with transaction.atomic():
        for record, _, code in to_save:
            if code:
                record.set_registration_code(code)
            record.save()

    created = sum(1 for _, is_new, _ in to_save if is_new)
    return created, len(to_save) - created