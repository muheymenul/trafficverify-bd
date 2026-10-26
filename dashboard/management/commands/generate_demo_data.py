"""
Creates FICTIONAL demo data for TrafficVerify BD.

Usage examples (run from the project folder, with (venv) active):

    python manage.py generate_demo_data              # create everything
    python manage.py generate_demo_data --only police
    python manage.py generate_demo_data --only vehicles
    python manage.py generate_demo_data --only drivers
    python manage.py generate_demo_data --reset      # delete demo data first

All names, IDs and numbers are fictional. Nothing here is a real record.
"""

import csv
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import PoliceRecord
from licences.models import Driver, DrivingLicence
from vehicles.models import Vehicle

TOTAL = 100

FIRST_NAMES = [
    "Arman", "Bilal", "Chandan", "Dipto", "Emon", "Farhan", "Galib", "Habib",
    "Imran", "Jahid", "Kamal", "Labib", "Mahin", "Nabil", "Omar", "Parvez",
    "Rafi", "Sabbir", "Tanvir", "Zahid", "Anika", "Bristy", "Chaity", "Disha",
    "Eshita", "Farzana", "Gulshan", "Hasina", "Ishrat", "Jui",
]
LAST_NAMES = [
    "Ahmed", "Bhuiyan", "Chowdhury", "Das", "Mondal", "Hossain", "Islam",
    "Khan", "Majumder", "Mia", "Paul", "Rahman", "Sarker", "Talukder",
    "Uddin", "Biswas", "Dey", "Haque", "Karim", "Sheikh",
]
UNITS = [
    "Demo Traffic Unit - Zone A", "Demo Traffic Unit - Zone B",
    "Demo Traffic Unit - Zone C", "Demo Highway Patrol 1",
    "Demo Highway Patrol 2", "Demo City Control Room",
    "Demo Traffic Unit - Zone D", "Demo Traffic Unit - Zone E",
]
RANKS = [
    PoliceRecord.Rank.CONSTABLE,
    PoliceRecord.Rank.CONSTABLE,
    PoliceRecord.Rank.NAIK,
    PoliceRecord.Rank.ASI,
    PoliceRecord.Rank.SI,
    PoliceRecord.Rank.INSPECTOR,
    PoliceRecord.Rank.ASP,
]

# Vehicle type + short code used inside the fictional registration number.
VT = Vehicle.VehicleType
VEHICLE_PATTERN = [
    (VT.MOTORCYCLE, "MC"), (VT.CAR, "CR"), (VT.MOTORCYCLE, "MC"),
    (VT.CNG, "CN"), (VT.CAR, "CR"), (VT.MOTORCYCLE, "MC"),
    (VT.PICKUP, "PK"), (VT.BUS, "BS"), (VT.TRUCK, "TK"), (VT.OTHER, "OT"),
]

LC = DrivingLicence.LicenceClass
LICENCE_CLASS_PATTERN = [
    LC.MOTORCYCLE, LC.LIGHT, LC.LIGHT, LC.MEDIUM, LC.HEAVY, LC.PROFESSIONAL,
]

# Letters/digits without look-alikes (no 0/O, 1/I) for easy typing.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def fake_name(i):
    """Same i always gives the same fictional name."""
    return f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {LAST_NAMES[(i * 7 + i // 3) % len(LAST_NAMES)]}"


def new_registration_code():
    """Random code like K7QM-X2PD-9WTA (12 characters)."""
    parts = ["".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(parts)


class Command(BaseCommand):
    help = "Create fictional demo police records, vehicles, drivers and licences."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=["police", "vehicles", "drivers"],
            help="Create only one kind of data.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="DELETE existing demo data of the selected kind(s) first.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Do not ask for confirmation when using --reset.",
        )

    # ------------------------------------------------------------
    def handle(self, *args, **options):
        only = options["only"]
        do_police = only in (None, "police")
        do_vehicles = only in (None, "vehicles")
        do_drivers = only in (None, "drivers")

        if options["reset"]:
            self.confirm_reset(options["yes"])
            self.reset(do_police, do_vehicles, do_drivers)

        self.today = timezone.localdate()

        if do_police:
            self.create_police()
        if do_vehicles:
            self.create_vehicles()
        if do_drivers:
            self.create_drivers()

        self.stdout.write(self.style.SUCCESS("Done. (All records are FICTIONAL demo data.)"))

    # ------------------------------------------------------------
    def confirm_reset(self, assume_yes):
        if assume_yes:
            return
        self.stdout.write(
            self.style.WARNING(
                "This will DELETE demo records (user accounts are NOT deleted)."
            )
        )
        answer = input("Type YES to continue: ")
        if answer.strip() != "YES":
            raise CommandError("Reset cancelled. Nothing was deleted.")

    @transaction.atomic
    def reset(self, do_police, do_vehicles, do_drivers):
        if do_police:
            count, _ = PoliceRecord.objects.all().delete()
            self.stdout.write(f"Deleted {count} police record(s).")
            codes_file = self.codes_file_path()
            if codes_file.exists():
                codes_file.unlink()
                self.stdout.write("Deleted the old registration codes file.")
        if do_vehicles:
            count, _ = Vehicle.objects.all().delete()
            self.stdout.write(f"Deleted {count} vehicle(s).")
        if do_drivers:
            # Deleting drivers also deletes their licences (CASCADE).
            count, _ = Driver.objects.all().delete()
            self.stdout.write(f"Deleted {count} driver/licence row(s).")

    def codes_file_path(self):
        return Path(settings.BASE_DIR) / "demo_output" / "police_registration_codes.csv"

    # ------------------------------------------------------------
    # Police records
    # ------------------------------------------------------------
    @transaction.atomic
    def create_police(self):
        self.stdout.write("Creating police records (hashing codes, may take a minute)...")
        created, skipped = 0, 0
        new_codes = []

        for i in range(1, TOTAL + 1):
            police_id = f"DEMO-P-{i:04d}"
            if PoliceRecord.objects.filter(demo_police_id=police_id).exists():
                skipped += 1
                continue

            code = new_registration_code()
            record = PoliceRecord(
                demo_police_id=police_id,
                full_name=fake_name(i),
                rank=RANKS[i % len(RANKS)],
                unit=UNITS[i % len(UNITS)],
                # Every 20th record is disabled so we can test "disabled record".
                is_eligible=(i % 20 != 0),
            )
            record.set_registration_code(code)
            record.save()
            new_codes.append((police_id, record.full_name, record.is_eligible, code))
            created += 1

        if new_codes:
            self.write_codes_file(new_codes)

        self.stdout.write(
            self.style.SUCCESS(f"Police records: {created} created, {skipped} already existed.")
        )

    def write_codes_file(self, rows):
        path = self.codes_file_path()
        path.parent.mkdir(exist_ok=True)
        is_new_file = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new_file:
                writer.writerow(["demo_police_id", "full_name", "eligible", "registration_code"])
            writer.writerows(rows)
        self.stdout.write(f"Registration codes saved to: {path}")
        self.stdout.write(
            self.style.WARNING("Keep this file private. It is excluded from Git.")
        )

    # ------------------------------------------------------------
    # Vehicles
    # ------------------------------------------------------------
    @transaction.atomic
    def create_vehicles(self):
        created, skipped = 0, 0
        today = self.today

        for i in range(TOTAL):
            vehicle_type, code = VEHICLE_PATTERN[i % len(VEHICLE_PATTERN)]
            number = f"DEMO-{code}-{1001 + i}"
            if Vehicle.objects.filter(registration_number=number).exists():
                skipped += 1
                continue

            # Valid documents expire between 60 and 360 days from today.
            future = lambda n: today + timedelta(days=60 + (i * n) % 300)
            tax = future(13)
            fitness = future(17)
            insurance = future(23)
            registration_status = Vehicle.RegistrationStatus.ACTIVE
            record_status = Vehicle.RecordStatus.ACTIVE

            # Motorcycles have no fitness certificate in this demo.
            if vehicle_type == VT.MOTORCYCLE:
                fitness = None

            # Predictable "problem" cases: one scenario per 11 vehicles.
            scenario = i % 11
            if scenario == 0:
                tax = today - timedelta(days=10 + i)
            elif scenario == 1:
                if fitness is not None:
                    fitness = today - timedelta(days=5 + i)
                else:
                    insurance = today - timedelta(days=5 + i)
            elif scenario == 2:
                insurance = today - timedelta(days=3 + i)
            elif scenario == 3:
                registration_status = Vehicle.RegistrationStatus.SUSPENDED
            elif scenario == 4:
                record_status = Vehicle.RecordStatus.INACTIVE
            elif scenario == 5:
                registration_status = Vehicle.RegistrationStatus.CANCELLED
            # scenarios 6-10 stay fully valid.

            Vehicle.objects.create(
                registration_number=number,
                vehicle_type=vehicle_type,
                owner_name=fake_name(i + 40),
                registration_status=registration_status,
                tax_token_expiry=tax,
                fitness_expiry=fitness,
                insurance_expiry=insurance,
                record_status=record_status,
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Vehicles: {created} created, {skipped} already existed.")
        )

    # ------------------------------------------------------------
    # Drivers and licences
    # ------------------------------------------------------------
    @transaction.atomic
    def create_drivers(self):
        created, skipped = 0, 0
        today = self.today

        for i in range(TOTAL):
            number = f"DEMO-DL-{100001 + i}"
            if DrivingLicence.objects.filter(licence_number=number).exists():
                skipped += 1
                continue

            scenario = i % 10
            status = DrivingLicence.Status.ACTIVE

            if scenario == 0:
                # Expired licence
                expiry = today - timedelta(days=20 + i)
            elif scenario == 3:
                # Valid but expires in 10 days
                expiry = today + timedelta(days=10)
            else:
                expiry = today + timedelta(days=100 + (i * 17) % 1500)

            if scenario == 1:
                status = DrivingLicence.Status.SUSPENDED
            elif scenario == 2:
                status = DrivingLicence.Status.REVOKED

            issue = expiry - timedelta(days=5 * 365)
            age_years = 28 + (i * 3) % 32  # ages 28 to 59
            birth_date = today - timedelta(days=age_years * 365 + (i * 11) % 300)

            driver = Driver.objects.create(
                full_name=fake_name(i + 15),
                date_of_birth=birth_date,
            )
            DrivingLicence.objects.create(
                driver=driver,
                licence_number=number,
                licence_class=LICENCE_CLASS_PATTERN[i % len(LICENCE_CLASS_PATTERN)],
                issue_date=issue,
                expiry_date=expiry,
                status=status,
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Drivers/licences: {created} created, {skipped} already existed.")
        )