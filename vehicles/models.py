from django.core.validators import RegexValidator
from django.db import models


registration_number_validator = RegexValidator(
    regex=r"^[A-Z0-9-]{5,20}$",
    message="Use only capital letters, numbers and hyphens (5-20 characters).",
)


class Vehicle(models.Model):
    """A FICTIONAL demo vehicle record. Not a real BRTA record."""

    class VehicleType(models.TextChoices):
        MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
        CAR = "CAR", "Private Car"
        BUS = "BUS", "Bus"
        TRUCK = "TRUCK", "Truck"
        PICKUP = "PICKUP", "Pickup / Microbus"
        CNG = "CNG", "CNG Auto-rickshaw"
        OTHER = "OTHER", "Other"

    class RegistrationStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        CANCELLED = "CANCELLED", "Cancelled"

    class RecordStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active record"
        INACTIVE = "INACTIVE", "Inactive record"

    registration_number = models.CharField(
        "Registration number",
        max_length=20,
        unique=True,
        validators=[registration_number_validator],
        help_text="Fictional number, for example DEMO-KA-1001",
    )
    vehicle_type = models.CharField(
        "Vehicle type", max_length=12, choices=VehicleType.choices
    )
    owner_name = models.CharField("Owner name (fictional)", max_length=120)
    registration_status = models.CharField(
        "Registration status",
        max_length=12,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.ACTIVE,
    )
    tax_token_expiry = models.DateField(
        "Tax token expiry date", null=True, blank=True
    )
    fitness_expiry = models.DateField(
        "Fitness certificate expiry date", null=True, blank=True
    )
    insurance_expiry = models.DateField(
        "Insurance expiry date", null=True, blank=True
    )
    record_status = models.CharField(
        "Record status",
        max_length=10,
        choices=RecordStatus.choices,
        default=RecordStatus.ACTIVE,
    )
    created_at = models.DateTimeField("Created at", auto_now_add=True)
    updated_at = models.DateTimeField("Updated at", auto_now=True)

    class Meta:
        ordering = ["registration_number"]
        verbose_name = "Vehicle (demo)"
        verbose_name_plural = "Vehicles (demo)"

    def save(self, *args, **kwargs):
        # Always store the registration number in UPPERCASE without spaces.
        self.registration_number = self.registration_number.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.registration_number} ({self.get_vehicle_type_display()})"