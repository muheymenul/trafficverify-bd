from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from licences.models import Driver, DrivingLicence
from vehicles.models import Vehicle

from .models import PoliceRecord
from .testutils import (
    FAST_HASHERS,
    make_admin,
    make_licence,
    make_officer,
    make_police_record,
    make_vehicle,
)

VEHICLE_HEADER = (
    "registration_number,vehicle_type,owner_name,registration_status,"
    "tax_token_expiry,fitness_expiry,insurance_expiry,record_status\n"
)
LICENCE_HEADER = "licence_number,driver_name,date_of_birth,licence_class,issue_date,expiry_date,status\n"
POLICE_HEADER = "demo_police_id,full_name,rank,unit,is_eligible,registration_code\n"


def upload(text, name="data.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class ImportTestMixin:
    """Shared helpers: log in as administrator and post a file."""

    import_url_name = ""

    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)
        self.url = reverse(self.import_url_name)

    def post_file(self, text, name="data.csv"):
        return self.client.post(self.url, {"file": upload(text, name)})

    def errors(self, resp):
        self.assertEqual(resp.status_code, 200)
        return resp.context["errors"]


# ---------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------
@FAST_HASHERS
class VehicleCsvTests(ImportTestMixin, TestCase):
    import_url_name = "admin:vehicles_vehicle_import_csv"

    GOOD = VEHICLE_HEADER + (
        "DEMO-CR-9101,CAR,Demo Owner One,ACTIVE,2028-12-31,2028-12-31,2028-12-31,ACTIVE\n"
        "DEMO-MC-9102,MOTORCYCLE,Demo Owner Two,ACTIVE,2028-06-30,,2028-06-30,ACTIVE\n"
        "DEMO-TK-9103,TRUCK,Demo Owner Three,ACTIVE,2020-01-01,2028-12-31,2028-12-31,ACTIVE\n"
    )

    def test_import_button_is_on_the_list_page(self):
        resp = self.client.get(reverse("admin:vehicles_vehicle_changelist"))
        self.assertContains(resp, "Import CSV")

    def test_good_file_creates_then_updates(self):
        resp = self.post_file(self.GOOD)
        self.assertRedirects(resp, reverse("admin:vehicles_vehicle_changelist"), fetch_redirect_response=False)
        self.assertEqual(Vehicle.objects.count(), 3)

        resp = self.client.post(self.url, {"file": upload(self.GOOD)}, follow=True)
        self.assertContains(resp, "0 created, 3 updated")
        self.assertEqual(Vehicle.objects.count(), 3)  # no duplicates

    def test_import_replaces_existing_values(self):
        make_vehicle("DEMO-CR-9101", owner_name="Old Name")
        self.post_file(self.GOOD)
        self.assertEqual(Vehicle.objects.get(registration_number="DEMO-CR-9101").owner_name, "Demo Owner One")

    def test_one_bad_row_means_nothing_is_saved(self):
        bad = VEHICLE_HEADER + (
            "DEMO-CR-9201,CAR,Demo Owner A,ACTIVE,2028-12-31,2028-12-31,2028-12-31,ACTIVE\n"
            "REAL-CR-9202,CAR,Demo Owner B,ACTIVE,2028-12-31,2028-12-31,2028-12-31,ACTIVE\n"
            "DEMO-CR-9203,SPACESHIP,Demo Owner C,ACTIVE,2028-12-31,2028-12-31,2028-12-31,ACTIVE\n"
            "DEMO-CR-9204,CAR,=1+1,ACTIVE,2028-12-31,2028-12-31,2028-12-31,ACTIVE\n"
            "DEMO-CR-9205,CAR,Demo Owner E,ACTIVE,31/12/2028,2028-12-31,2028-12-31,ACTIVE\n"
            "DEMO-CR-9201,CAR,Demo Owner F,ACTIVE,2028-12-31,2028-12-31,2028-12-31,ACTIVE\n"
        )
        errors = self.errors(self.post_file(bad))
        text = "\n".join(errors)
        for line in ("Row 3:", "Row 4:", "Row 5:", "Row 6:", "Row 7:"):
            self.assertIn(line, text)
        self.assertNotIn("Row 2:", text)  # the good row has no problem...
        self.assertEqual(Vehicle.objects.count(), 0)  # ...but it was not saved either

    def test_formula_cells_are_rejected(self):
        for cell in ["=1+1", "+1", "-1", "@SUM(1)"]:
            with self.subTest(cell=cell):
                text = VEHICLE_HEADER + f"DEMO-CR-9301,CAR,{cell},ACTIVE,,,,ACTIVE\n"
                self.assertTrue(any("formula" in e for e in self.errors(self.post_file(text))))
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_real_looking_numbers_are_rejected(self):
        text = VEHICLE_HEADER + "DHAKA-METRO-1234,CAR,Someone,ACTIVE,,,,ACTIVE\n"
        self.assertTrue(any("DEMO-" in e for e in self.errors(self.post_file(text))))

    def test_wrong_file_type_is_rejected(self):
        resp = self.post_file(self.GOOD, name="data.txt")
        self.assertIn("file", resp.context["form"].errors)
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_file_over_1mb_is_rejected(self):
        big = SimpleUploadedFile("big.csv", b"a" * 1_000_001, content_type="text/csv")
        resp = self.client.post(self.url, {"file": big})
        self.assertIn("file", resp.context["form"].errors)

    def test_not_utf8_is_rejected(self):
        bad = SimpleUploadedFile("bad.csv", b"\xff\xfe\x00broken", content_type="text/csv")
        resp = self.client.post(self.url, {"file": bad})
        self.assertTrue(any("UTF-8" in e for e in resp.context["errors"]))

    def test_empty_and_header_only_files(self):
        resp = self.post_file("")  # Django itself refuses an empty upload
        self.assertIn("file", resp.context["form"].errors)
        self.assertEqual(Vehicle.objects.count(), 0)
        self.assertTrue(any("no data rows" in e for e in self.errors(self.post_file(VEHICLE_HEADER))))

    def test_missing_and_unknown_columns(self):
        text = "registration_number,vehicle_type,colour\nDEMO-CR-9401,CAR,red\n"
        joined = "\n".join(self.errors(self.post_file(text)))
        self.assertIn("Missing column", joined)
        self.assertIn("Unknown column", joined)

    def test_too_many_rows(self):
        rows = "".join(f"DEMO-CR-{i:05d},CAR,Owner,ACTIVE,,,,ACTIVE\n" for i in range(501))
        self.assertTrue(any("Too many rows" in e for e in self.errors(self.post_file(VEHICLE_HEADER + rows))))
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_officer_can_not_import(self):
        officer_client = Client()
        officer_client.force_login(make_officer())
        resp = officer_client.post(self.url, {"file": upload(self.GOOD)})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_export_escapes_formulas_and_keeps_all_columns(self):
        vehicle = make_vehicle(owner_name="=1+1")
        resp = self.client.post(
            reverse("admin:vehicles_vehicle_changelist"),
            {"action": "export_csv", "_selected_action": [vehicle.pk]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/csv")
        text = resp.content.decode("utf-8-sig")
        self.assertTrue(text.startswith("registration_number,vehicle_type,owner_name"))
        self.assertIn("DEMO-CR-1001", text)
        self.assertIn("'=1+1", text)       # a leading ' stops Excel running it as a formula
        self.assertNotIn(",=1+1", text)


# ---------------------------------------------------------------
# Licences
# ---------------------------------------------------------------
@FAST_HASHERS
class LicenceCsvTests(ImportTestMixin, TestCase):
    import_url_name = "admin:licences_drivinglicence_import_csv"

    GOOD = LICENCE_HEADER + (
        "DEMO-DL-900001,Demo Driver One,1990-05-15,LIGHT,2023-01-10,2028-01-10,ACTIVE\n"
        "DEMO-DL-900002,Demo Driver Two,1985-11-02,MOTORCYCLE,2018-03-01,2023-03-01,ACTIVE\n"
    )

    def test_good_file_creates_drivers_and_licences(self):
        self.post_file(self.GOOD)
        self.assertEqual(DrivingLicence.objects.count(), 2)
        self.assertEqual(Driver.objects.count(), 2)

    def test_importing_again_updates_without_duplicates(self):
        self.post_file(self.GOOD)
        changed = self.GOOD.replace("Demo Driver One", "Renamed Driver")
        resp = self.client.post(self.url, {"file": upload(changed)}, follow=True)
        self.assertContains(resp, "0 created, 2 updated")
        self.assertEqual(Driver.objects.count(), 2)
        self.assertEqual(
            DrivingLicence.objects.get(licence_number="DEMO-DL-900001").driver.full_name,
            "Renamed Driver",
        )

    def test_invalid_rows_are_rejected_and_nothing_saved(self):
        bad = LICENCE_HEADER + (
            "DEMO-DL-900011,Good Row,1990-05-15,LIGHT,2023-01-10,2028-01-10,ACTIVE\n"
            "DEMO-DL-900012,Bad Dates,1990-05-15,LIGHT,2028-01-10,2023-01-10,ACTIVE\n"
            "DEMO-DL-900013,Future Birth,2999-01-01,LIGHT,2023-01-10,2028-01-10,ACTIVE\n"
            "DEMO-DL-900014,Bad Class,1990-05-15,ROCKET,2023-01-10,2028-01-10,ACTIVE\n"
            "REAL-DL-900015,Real Prefix,1990-05-15,LIGHT,2023-01-10,2028-01-10,ACTIVE\n"
        )
        text = "\n".join(self.errors(self.post_file(bad)))
        for line in ("Row 3:", "Row 4:", "Row 5:", "Row 6:"):
            self.assertIn(line, text)
        self.assertEqual(DrivingLicence.objects.count(), 0)
        self.assertEqual(Driver.objects.count(), 0)

    def test_expired_imported_licence_is_reported_as_expired(self):
        from verification.services import check_licence

        self.post_file(self.GOOD)
        old = DrivingLicence.objects.get(licence_number="DEMO-DL-900002")
        self.assertEqual(check_licence(old).category, "EXPIRED")

    def test_export_has_expected_columns(self):
        licence = make_licence()
        resp = self.client.post(
            reverse("admin:licences_drivinglicence_changelist"),
            {"action": "export_csv", "_selected_action": [licence.pk]},
        )
        text = resp.content.decode("utf-8-sig")
        self.assertTrue(text.startswith("licence_number,driver_name,date_of_birth"))
        self.assertIn("DEMO-DL-100001", text)


# ---------------------------------------------------------------
# Police records
# ---------------------------------------------------------------
@FAST_HASHERS
class PoliceCsvTests(ImportTestMixin, TestCase):
    import_url_name = "admin:accounts_policerecord_import_csv"

    GOOD = POLICE_HEADER + (
        "DEMO-P-9101,Demo Officer Import One,SI,Demo Traffic Unit - Zone A,true,ImportCode-9101\n"
        "DEMO-P-9102,Demo Officer Import Two,CONSTABLE,Demo Traffic Unit - Zone B,false,ImportCode-9102\n"
    )

    def test_good_file_creates_records_with_hashed_codes(self):
        self.post_file(self.GOOD)
        one = PoliceRecord.objects.get(demo_police_id="DEMO-P-9101")
        two = PoliceRecord.objects.get(demo_police_id="DEMO-P-9102")
        self.assertTrue(one.check_registration_code("ImportCode-9101"))
        self.assertNotIn("ImportCode-9101", one.registration_code_hash)
        self.assertTrue(one.is_eligible)
        self.assertFalse(two.is_eligible)

    def test_new_record_needs_a_code(self):
        text = POLICE_HEADER + "DEMO-P-9201,No Code,SI,Unit,true,\n"
        self.assertTrue(any("registration_code" in e for e in self.errors(self.post_file(text))))
        self.assertEqual(PoliceRecord.objects.count(), 0)

    def test_short_code_and_bad_values_are_rejected(self):
        text = POLICE_HEADER + (
            "DEMO-P-9301,Short Code,SI,Unit,true,abc\n"
            "REAL-P-9302,Wrong Prefix,SI,Unit,true,LongEnoughCode1\n"
            "DEMO-P-9303,Bad Rank,GENERAL,Unit,true,LongEnoughCode2\n"
            "DEMO-P-9304,Bad Bool,SI,Unit,maybe,LongEnoughCode3\n"
        )
        text_errors = "\n".join(self.errors(self.post_file(text)))
        for line in ("Row 2:", "Row 3:", "Row 4:", "Row 5:"):
            self.assertIn(line, text_errors)
        self.assertEqual(PoliceRecord.objects.count(), 0)

    def test_existing_record_keeps_its_code_when_code_cell_is_empty(self):
        make_police_record("DEMO-P-9401", code="OriginalCode-1")
        text = POLICE_HEADER + "DEMO-P-9401,Renamed Person,ASI,New Unit,false,\n"
        self.post_file(text)
        record = PoliceRecord.objects.get(demo_police_id="DEMO-P-9401")
        self.assertEqual(record.full_name, "Renamed Person")
        self.assertFalse(record.is_eligible)
        self.assertTrue(record.check_registration_code("OriginalCode-1"))

    def test_errors_never_repeat_the_secret_code(self):
        text = POLICE_HEADER + "REAL-P-9501,Wrong Prefix,SI,Unit,true,SecretCode-XYZ\n"
        errors = self.errors(self.post_file(text))
        self.assertNotIn("SecretCode-XYZ", "\n".join(errors))

    def test_export_never_contains_codes_or_hashes(self):
        record = make_police_record("DEMO-P-9601", code="ExportSecret-1")
        resp = self.client.post(
            reverse("admin:accounts_policerecord_changelist"),
            {"action": "export_csv", "_selected_action": [record.pk]},
        )
        text = resp.content.decode("utf-8-sig")
        self.assertIn("DEMO-P-9601", text)
        self.assertNotIn("registration_code", text)
        self.assertNotIn("ExportSecret-1", text)
        self.assertNotIn(record.registration_code_hash, text)