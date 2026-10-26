"""
Verification rules for the DEMO database.

IMPORTANT: "VALID" here only means "valid according to the fictional demo
records". It never means a vehicle or licence is legally valid in Bangladesh.
"""

from dataclasses import dataclass, field
from datetime import date

from django.utils import timezone

from licences.models import DrivingLicence
from vehicles.models import Vehicle

from .models import VerificationLog

Result = VerificationLog.ResultCategory
VT = Vehicle.VehicleType

EXPIRING_SOON_DAYS = 30


class DocStatus:
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    UNVERIFIED = "UNVERIFIED"
    NOT_REQUIRED = "NOT_REQUIRED"


STATUS_LABELS = {
    DocStatus.VALID: "Valid",
    DocStatus.EXPIRED: "Expired",
    DocStatus.UNVERIFIED: "Unverified",
    DocStatus.NOT_REQUIRED: "Not required",
}

# ---------------------------------------------------------------
# DEMONSTRATION RULES (fictional): which documents each vehicle type needs.
# Vehicle types not listed here need all three documents.
# ---------------------------------------------------------------
ALL_DOCUMENTS = ("tax_token", "fitness", "insurance")
REQUIRED_DOCUMENTS = {
    VT.MOTORCYCLE: ("tax_token", "insurance"),
}

# key -> (label shown on screen, field name on the Vehicle model)
DOCUMENT_FIELDS = {
    "tax_token": ("Tax token", "tax_token_expiry"),
    "fitness": ("Fitness certificate", "fitness_expiry"),
    "insurance": ("Insurance", "insurance_expiry"),
}


# ---------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------
@dataclass
class DocumentCheck:
    name: str
    status: str
    expiry_date: date | None
    days_left: int | None

    @property
    def label(self):
        return STATUS_LABELS[self.status]

    @property
    def expiring_soon(self):
        return (
            self.status == DocStatus.VALID
            and self.days_left is not None
            and self.days_left <= EXPIRING_SOON_DAYS
        )


@dataclass
class Outcome:
    category: str
    documents: list = field(default_factory=list)
    reasons: list = field(default_factory=list)


# ---------------------------------------------------------------
# Rules
# ---------------------------------------------------------------
def document_status(expiry_date, required, today):
    """The expiry date itself is still valid; the next day is expired."""
    if not required:
        return DocStatus.NOT_REQUIRED
    if expiry_date is None:
        return DocStatus.UNVERIFIED
    if expiry_date < today:
        return DocStatus.EXPIRED
    return DocStatus.VALID


def check_vehicle(vehicle, today=None):
    today = today or timezone.localdate()
    required = REQUIRED_DOCUMENTS.get(vehicle.vehicle_type, ALL_DOCUMENTS)

    documents = []
    reasons = []

    for key, (label, field_name) in DOCUMENT_FIELDS.items():
        expiry = getattr(vehicle, field_name)
        status = document_status(expiry, key in required, today)
        days_left = None
        if expiry is not None and status != DocStatus.NOT_REQUIRED:
            days_left = (expiry - today).days
        documents.append(DocumentCheck(label, status, expiry, days_left))

        if status == DocStatus.EXPIRED:
            reasons.append(f"{label} expired on {expiry:%d %b %Y}.")
        elif status == DocStatus.UNVERIFIED:
            reasons.append(
                f"{label} is required but no expiry date is recorded, "
                "so it can not be verified."
            )

    registration_ok = vehicle.registration_status == Vehicle.RegistrationStatus.ACTIVE
    record_ok = vehicle.record_status == Vehicle.RecordStatus.ACTIVE

    if not registration_ok:
        reasons.insert(
            0,
            "Registration status in the demo database is "
            f"{vehicle.get_registration_status_display()}.",
        )
    if not record_ok:
        reasons.insert(
            0,
            "This demo record is marked inactive, so it can not be relied on.",
        )

    statuses = [d.status for d in documents]
    if not registration_ok:
        category = Result.INVALID
    elif not record_ok:
        category = Result.UNVERIFIED
    elif DocStatus.EXPIRED in statuses:
        category = Result.EXPIRED
    elif DocStatus.UNVERIFIED in statuses:
        category = Result.UNVERIFIED
    else:
        category = Result.VALID

    return Outcome(category=category, documents=documents, reasons=reasons)


def check_licence(licence, today=None):
    today = today or timezone.localdate()
    reasons = []

    status_ok = licence.status == DrivingLicence.Status.ACTIVE
    expired = licence.expiry_date < today

    if not status_ok:
        reasons.append(
            f"Licence status in the demo database is {licence.get_status_display()}."
        )
    if expired:
        reasons.append(f"Licence expired on {licence.expiry_date:%d %b %Y}.")

    if not status_ok:
        category = Result.INVALID
    elif expired:
        category = Result.EXPIRED
    else:
        category = Result.VALID

    return Outcome(category=category, reasons=reasons)


# ---------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------
def record_verification(officer, verification_type, identifier, category):
    """Save one audit log row. Never pass passwords or codes here."""
    return VerificationLog.objects.create(
        officer=officer,
        verification_type=verification_type,
        searched_identifier=identifier,
        result_category=category,
    )


def previous_check(officer, verification_type, identifier, exclude_pk):
    """The same officer's most recent earlier check of the same number."""
    return (
        VerificationLog.objects.filter(
            officer=officer,
            verification_type=verification_type,
            searched_identifier=identifier,
        )
        .exclude(pk=exclude_pk)
        .first()
    )