import re

from django.conf import settings
from django.db import models

IDENTIFIER_PATTERN = re.compile(r"^[A-Z0-9-]{5,20}$")


class AuditLogQuerySet(models.QuerySet):
    """A queryset that only allows adding rows, never changing or deleting."""

    def update(self, **kwargs):
        raise PermissionError("Verification logs can not be updated.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise PermissionError("Verification logs can not be updated.")

    def delete(self):
        raise PermissionError("Verification logs can not be deleted.")


class VerificationLog(models.Model):
    """
    One row = one search done by a logged-in officer (audit log).

    Rules:
    - Never store passwords or registration codes here.
    - A saved log entry can not be edited or deleted (protects the audit trail).
    """

    class VerificationType(models.TextChoices):
        VEHICLE = "VEHICLE", "Vehicle"
        LICENCE = "LICENCE", "Driving Licence"

    class ResultCategory(models.TextChoices):
        VALID = "VALID", "Valid"
        EXPIRED = "EXPIRED", "Expired"
        INVALID = "INVALID", "Invalid"
        UNVERIFIED = "UNVERIFIED", "Unverified"
        NOT_FOUND = "NOT_FOUND", "No record found in demo database"

    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verification_logs",
        verbose_name="Officer",
    )
    verification_type = models.CharField(
        "Verification type", max_length=10, choices=VerificationType.choices
    )
    searched_identifier = models.CharField(
        "Searched registration / licence number", max_length=30
    )
    result_category = models.CharField(
        "Result", max_length=12, choices=ResultCategory.choices
    )
    created_at = models.DateTimeField("Date and time", auto_now_add=True, db_index=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Verification log"
        verbose_name_plural = "Verification logs"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Verification logs can not be modified once saved.")

        self.searched_identifier = self.searched_identifier.strip().upper()
        # Only a plain registration / licence number may be logged. This keeps
        # passwords, codes and other free text out of the audit trail.
        if not IDENTIFIER_PATTERN.match(self.searched_identifier):
            raise ValueError("Only a registration or licence number can be logged.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Verification logs can not be deleted.")

    @property
    def masked_identifier(self):
        """Show only the first 4 and last 2 characters, e.g. DEMO*********01"""
        value = self.searched_identifier
        if len(value) <= 6:
            return value
        return value[:4] + "*" * (len(value) - 6) + value[-2:]

    def __str__(self):
        return f"{self.officer} - {self.get_verification_type_display()} - {self.created_at:%Y-%m-%d %H:%M}"