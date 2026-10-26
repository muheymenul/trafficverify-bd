from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for TrafficVerify BD (DEMO project).

    Keeps everything from Django's normal user (username, password hash,
    is_active, etc.) and adds a role so we can separate administrators
    from police officers on the server side.
    """

    class Role(models.TextChoices):
        ADMINISTRATOR = "ADMIN", "Administrator"
        OFFICER = "OFFICER", "Police Officer"

    role = models.CharField(
        "Role",
        max_length=10,
        choices=Role.choices,
        default=Role.OFFICER,
    )

    def save(self, *args, **kwargs):
        # A superuser (created with createsuperuser) is always an Administrator.
        if self.is_superuser:
            self.role = self.Role.ADMINISTRATOR
        super().save(*args, **kwargs)

    @property
    def is_administrator(self):
        return self.role == self.Role.ADMINISTRATOR

    @property
    def is_officer(self):
        return self.role == self.Role.OFFICER

    def __str__(self):
        return self.username


class PoliceRecord(models.Model):
    """
    A FICTIONAL demo police record. It is NOT a real police identity.

    A person can register only if their Demo Police ID exists here, the
    record is eligible, it is not already claimed, and they know the
    one-time registration code.
    """

    class Rank(models.TextChoices):
        CONSTABLE = "CONSTABLE", "Constable"
        NAIK = "NAIK", "Naik"
        ASI = "ASI", "Assistant Sub-Inspector"
        SI = "SI", "Sub-Inspector"
        INSPECTOR = "INSPECTOR", "Inspector"
        ASP = "ASP", "Assistant Superintendent"

    demo_police_id = models.CharField(
        "Demo Police ID",
        max_length=20,
        unique=True,
        help_text="Fictional ID, for example DEMO-P-0001",
    )
    full_name = models.CharField("Full name (fictional)", max_length=120)
    rank = models.CharField("Rank", max_length=20, choices=Rank.choices)
    unit = models.CharField("Unit", max_length=100)

    # The registration code is stored HASHED (like a password), never as plain text.
    registration_code_hash = models.CharField(
        "Registration code (hashed)", max_length=128, blank=True, editable=False
    )

    is_eligible = models.BooleanField(
        "Eligible to register",
        default=True,
        help_text="Untick to disable this record.",
    )

    # One user can claim one record, and one record can be claimed by one user.
    claimed_by = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="police_profile",
        verbose_name="Claimed by user",
    )
    claimed_at = models.DateTimeField("Claimed at", null=True, blank=True)
    created_at = models.DateTimeField("Created at", auto_now_add=True)

    class Meta:
        ordering = ["demo_police_id"]
        verbose_name = "Police record (demo)"
        verbose_name_plural = "Police records (demo)"

    def save(self, *args, **kwargs):
        # Always store the ID in UPPERCASE without spaces.
        self.demo_police_id = self.demo_police_id.strip().upper()
        super().save(*args, **kwargs)

    def set_registration_code(self, raw_code):
        """Hash and store a registration code. Call save() afterwards."""
        self.registration_code_hash = make_password(raw_code.strip())

    def check_registration_code(self, raw_code):
        """Return True only if raw_code matches the stored hash."""
        if not self.registration_code_hash:
            return False
        return check_password(raw_code.strip(), self.registration_code_hash)

    @property
    def is_claimed(self):
        return self.claimed_by_id is not None

    def __str__(self):
        return f"{self.demo_police_id} - {self.full_name} ({self.get_rank_display()})"