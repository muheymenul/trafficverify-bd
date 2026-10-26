"""Helpers shared by all automated tests (not a test file itself)."""

from datetime import date, timedelta

from django.test import override_settings
from django.utils import timezone

from licences.models import Driver, DrivingLicence
from vehicles.models import Vehicle

from .models import PoliceRecord, User

# Tests only: a fast password hasher so hundreds of users can be made quickly.
# Real settings are NOT changed.
FAST_HASHERS = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)

PASSWORD = "Str0ng-Test-Pass-77"
CODE = "TestCode-1234"


def make_police_record(police_id="DEMO-P-0001", code=CODE, **kwargs):
    data = dict(
        demo_police_id=police_id,
        full_name="Test Officer",
        rank=PoliceRecord.Rank.SI,
        unit="Demo Unit",
    )
    data.update(kwargs)
    record = PoliceRecord(**data)
    record.set_registration_code(code)
    record.save()
    return record


def make_officer(username="officer1", police_id="DEMO-P-0001", password=PASSWORD, **record_kwargs):
    """An officer whose demo police record is already claimed."""
    record = make_police_record(police_id, **record_kwargs)
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role=User.Role.OFFICER,
    )
    record.claimed_by = user
    record.claimed_at = timezone.now()
    record.save()
    return user


def make_admin(username="admin1", password=PASSWORD):
    return User.objects.create_superuser(
        username=username, email=f"{username}@example.com", password=password
    )


def make_vehicle(number="DEMO-CR-1001", vehicle_type=Vehicle.VehicleType.CAR, **kwargs):
    soon = timezone.localdate() + timedelta(days=100)
    data = dict(
        registration_number=number,
        vehicle_type=vehicle_type,
        owner_name="Demo Owner",
        tax_token_expiry=soon,
        fitness_expiry=soon,
        insurance_expiry=soon,
    )
    data.update(kwargs)
    return Vehicle.objects.create(**data)


def make_licence(number="DEMO-DL-100001", name="Demo Driver", **kwargs):
    today = timezone.localdate()
    driver = Driver.objects.create(
        full_name=name, date_of_birth=kwargs.pop("date_of_birth", date(1971, 2, 3))
    )
    data = dict(
        driver=driver,
        licence_number=number,
        licence_class=DrivingLicence.LicenceClass.LIGHT,
        issue_date=today - timedelta(days=365),
        expiry_date=today + timedelta(days=365),
        status=DrivingLicence.Status.ACTIVE,
    )
    data.update(kwargs)
    return DrivingLicence.objects.create(**data)