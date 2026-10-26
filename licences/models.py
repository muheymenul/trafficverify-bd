from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


licence_number_validator = RegexValidator(
    regex=r"^[A-Z0-9-]{5,20}$",
    message="Use only capital letters, numbers and hyphens (5-20 characters).",
)


class Driver(models.Model):
    """A FICTIONAL demo driver. Not a real person."""

    full_name = models.CharField("Full name (fictional)", max_length=120)
    date_of_birth = models.DateField("Date of birth (fictional)")
    photo = models.ImageField(
        "Demo photo",
        upload_to="driver_photos/",
        null=True,
        blank=True,
        help_text="Use only fictional or authorised sample images.",
    )
    created_at = models.DateTimeField("Created at", auto_now_add=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Driver (demo)"
        verbose_name_plural = "Drivers (demo)"

    def __str__(self):
        return self.full_name


class DrivingLicence(models.Model):
    """A FICTIONAL demo driving licence. Not a real government licence."""

    class LicenceClass(models.TextChoices):
        MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
        LIGHT = "LIGHT", "Light Vehicle"
        MEDIUM = "MEDIUM", "Medium Vehicle"
        HEAVY = "HEAVY", "Heavy Vehicle"
        PROFESSIONAL = "PROFESSIONAL", "Professional"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        REVOKED = "REVOKED", "Revoked"

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="licences",
        verbose_name="Driver",
    )
    licence_number = models.CharField(
        "Licence number",
        max_length=20,
        unique=True,
        validators=[licence_number_validator],
        help_text="Fictional number, for example DEMO-DL-100001",
    )
    licence_class = models.CharField(
        "Licence class", max_length=15, choices=LicenceClass.choices
    )
    issue_date = models.DateField("Issue date")
    expiry_date = models.DateField("Expiry date")
    status = models.CharField(
        "Licence status",
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField("Created at", auto_now_add=True)
    updated_at = models.DateTimeField("Updated at", auto_now=True)

    class Meta:
        ordering = ["licence_number"]
        verbose_name = "Driving licence (demo)"
        verbose_name_plural = "Driving licences (demo)"

    def clean(self):
        super().clean()
        if self.issue_date and self.expiry_date and self.expiry_date <= self.issue_date:
            raise ValidationError("Expiry date must be after the issue date.")

    def save(self, *args, **kwargs):
        self.licence_number = self.licence_number.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.licence_number} - {self.driver.full_name}"