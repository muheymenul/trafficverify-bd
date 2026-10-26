import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import PoliceRecord, User
from accounts.testutils import (
    CODE,
    FAST_HASHERS,
    PASSWORD,
    make_admin,
    make_licence,
    make_officer,
    make_vehicle,
)
from licences.models import Driver, DrivingLicence
from vehicles.models import Vehicle
from verification.models import VerificationLog
from verification.services import check_licence, check_vehicle


def add_log(user, identifier="DEMO-MC-1001", vtype="VEHICLE", result="VALID"):
    return VerificationLog.objects.create(
        officer=user,
        verification_type=vtype,
        searched_identifier=identifier,
        result_category=result,
    )


# ---------------------------------------------------------------
# Officer panel
# ---------------------------------------------------------------
@FAST_HASHERS
class OfficerPanelTests(TestCase):
    def setUp(self):
        self.user = make_officer()
        self.client.force_login(self.user)

    def test_protected_pages_need_login(self):
        anon = Client()
        for name in ["dashboard:home", "dashboard:history", "dashboard:settings", "dashboard:password_change"]:
            with self.subTest(page=name):
                resp = anon.get(reverse(name))
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp["Location"].startswith(reverse("accounts:login")))

    def test_dashboard_shows_officer_details_and_counts(self):
        add_log(self.user)
        add_log(self.user, "DEMO-CR-1002", result="EXPIRED")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertContains(resp, "Test Officer")
        self.assertContains(resp, "DEMO-P-0001")
        self.assertContains(resp, "DEMO SYSTEM")
        self.assertEqual(resp.context["total_count"], 2)
        self.assertEqual(resp.context["today_count"], 2)

    def test_dashboard_with_no_history(self):
        resp = self.client.get(reverse("dashboard:home"))
        self.assertContains(resp, "No verifications yet")

    def test_history_shows_only_my_logs(self):
        other = make_officer(username="officer2", police_id="DEMO-P-0002")
        mine = add_log(self.user, "DEMO-MC-1001")
        add_log(other, "DEMO-MC-2002")
        resp = self.client.get(reverse("dashboard:history"))
        shown = list(resp.context["page_obj"].object_list)
        self.assertEqual(shown, [mine])
        self.assertNotContains(resp, "DEMO******02")

    def test_history_filters(self):
        add_log(self.user, "DEMO-MC-1001", "VEHICLE", "VALID")
        add_log(self.user, "DEMO-CR-1002", "VEHICLE", "EXPIRED")
        add_log(self.user, "DEMO-DL-100001", "LICENCE", "NOT_FOUND")
        url = reverse("dashboard:history")

        self.assertEqual(len(self.client.get(url, {"type": "VEHICLE"}).context["page_obj"].object_list), 2)
        self.assertEqual(len(self.client.get(url, {"result": "EXPIRED"}).context["page_obj"].object_list), 1)

        resp = self.client.get(url, {"type": "HACK", "result": "NOPE"})  # unknown values are ignored
        self.assertEqual(resp.context["selected_type"], "")
        self.assertEqual(len(resp.context["page_obj"].object_list), 3)

    def test_history_pagination(self):
        for i in range(12):
            add_log(self.user, f"DEMO-CR-10{i:02d}")
        url = reverse("dashboard:history")
        self.assertEqual(len(self.client.get(url).context["page_obj"].object_list), 10)
        self.assertEqual(len(self.client.get(url, {"page": 2}).context["page_obj"].object_list), 2)

    def test_history_has_no_edit_or_delete_controls(self):
        add_log(self.user)
        resp = self.client.get(reverse("dashboard:history"))
        self.assertNotContains(resp, "Delete")
        self.assertNotContains(resp, "Edit")

    def test_settings_page(self):
        resp = self.client.get(reverse("dashboard:settings"))
        self.assertContains(resp, "officer1")
        self.assertContains(resp, "DEMO-P-0001")
        self.assertNotContains(resp, self.user.password)  # the hash is never shown

    def test_password_change_success_keeps_user_logged_in(self):
        new = "An0ther-Str0ng-Pass-88"
        resp = self.client.post(
            reverse("dashboard:password_change"),
            {"old_password": PASSWORD, "new_password1": new, "new_password2": new},
        )
        self.assertRedirects(resp, reverse("dashboard:settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)

    def test_password_change_needs_correct_old_password(self):
        new = "An0ther-Str0ng-Pass-88"
        resp = self.client.post(
            reverse("dashboard:password_change"),
            {"old_password": "wrong", "new_password1": new, "new_password2": new},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_officer_can_not_open_admin_dashboard(self):
        for name in ["adminpanel:home", "adminpanel:officers", "adminpanel:vehicles",
                     "adminpanel:licences", "adminpanel:logs"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_officer_can_not_see_another_officers_private_data(self):
        other = make_officer(username="officer2", police_id="DEMO-P-0002", full_name="Second Person")
        resp = self.client.get(reverse("dashboard:settings"))
        self.assertNotContains(resp, "Second Person")
        self.assertNotContains(resp, other.email)


# ---------------------------------------------------------------
# Admin dashboard (/panel/)
# ---------------------------------------------------------------
PANEL_PAGES = ["adminpanel:home", "adminpanel:officers", "adminpanel:vehicles",
               "adminpanel:licences", "adminpanel:logs"]


@FAST_HASHERS
class AdminPanelTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.officer = make_officer()
        self.client.force_login(self.admin)

    def test_anonymous_is_sent_to_login(self):
        anon = Client()
        for name in PANEL_PAGES:
            with self.subTest(page=name):
                resp = anon.get(reverse(name))
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp["Location"].startswith(reverse("accounts:login")))

    def test_administrator_can_open_all_pages(self):
        for name in PANEL_PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_administrator_without_staff_flag_is_refused(self):
        weak = User.objects.create_user("weakadmin", password=PASSWORD, role=User.Role.ADMINISTRATOR)
        client = Client()
        client.force_login(weak)
        self.assertEqual(client.get(reverse("adminpanel:home")).status_code, 403)

    def test_summary_numbers(self):
        make_vehicle()
        make_vehicle("DEMO-CR-1002")
        make_licence()
        add_log(self.officer)
        resp = self.client.get(reverse("adminpanel:home"))
        self.assertEqual(resp.context["officer_total"], 1)
        self.assertEqual(resp.context["vehicle_total"], 2)
        self.assertEqual(resp.context["licence_total"], 1)
        self.assertEqual(resp.context["log_total"], 1)
        self.assertEqual(resp.context["police_claimed"], 1)

    def test_logs_page_shows_full_numbers_to_administrators(self):
        add_log(self.officer, "DEMO-MC-1001")
        resp = self.client.get(reverse("adminpanel:logs"))
        self.assertContains(resp, "DEMO-MC-1001")
        self.assertContains(resp, "DEMO-P-0001")

    def test_logs_filters(self):
        add_log(self.officer, "DEMO-MC-1001", "VEHICLE", "VALID")
        add_log(self.officer, "DEMO-DL-100001", "LICENCE", "EXPIRED")
        url = reverse("adminpanel:logs")
        self.assertEqual(len(self.client.get(url, {"type": "LICENCE"}).context["page_obj"].object_list), 1)
        self.assertEqual(len(self.client.get(url, {"q": "mc-1001"}).context["page_obj"].object_list), 1)
        self.assertEqual(len(self.client.get(url, {"q": "DEMO-P-0001"}).context["page_obj"].object_list), 2)
        # a broken date must not crash the page
        self.assertEqual(self.client.get(url, {"from": "not-a-date", "to": "2024-13-45"}).status_code, 200)

    def test_vehicle_result_filter(self):
        from datetime import timedelta
        from django.utils import timezone

        yesterday = timezone.localdate() - timedelta(days=1)
        make_vehicle("DEMO-CR-1001")
        make_vehicle("DEMO-CR-1002", tax_token_expiry=yesterday)
        make_vehicle("DEMO-CR-1003", registration_status="SUSPENDED")
        url = reverse("adminpanel:vehicles")

        def numbers(params):
            page = self.client.get(url, params).context["page_obj"]
            return {v.registration_number for v in page.object_list}

        self.assertEqual(numbers({"result": "EXPIRED"}), {"DEMO-CR-1002"})
        self.assertEqual(numbers({"result": "VALID"}), {"DEMO-CR-1001"})
        self.assertEqual(numbers({"result": "INVALID"}), {"DEMO-CR-1003"})
        self.assertEqual(len(numbers({"result": "HACK"})), 3)  # unknown value is ignored

    def test_licence_result_filter(self):
        from datetime import timedelta
        from django.utils import timezone

        yesterday = timezone.localdate() - timedelta(days=1)
        make_licence("DEMO-DL-100001")
        make_licence("DEMO-DL-100002", expiry_date=yesterday)
        resp = self.client.get(reverse("adminpanel:licences"), {"result": "EXPIRED"})
        numbers = {l.licence_number for l in resp.context["page_obj"].object_list}
        self.assertEqual(numbers, {"DEMO-DL-100002"})

    def test_search_text_is_escaped(self):
        resp = self.client.get(reverse("adminpanel:vehicles"), {"q": "<script>alert(1)</script>"})
        self.assertNotContains(resp, "<script>alert(1)</script>")
        self.assertContains(resp, "&lt;script&gt;")

    def test_officers_list_shows_search_counts(self):
        add_log(self.officer)
        add_log(self.officer, "DEMO-CR-1002")
        resp = self.client.get(reverse("adminpanel:officers"))
        row = resp.context["page_obj"].object_list[0]
        self.assertEqual(row.log_count, 2)
        self.assertEqual(len(self.client.get(reverse("adminpanel:officers"), {"status": "inactive"})
                             .context["page_obj"].object_list), 0)


# ---------------------------------------------------------------
# Demo data generator
# ---------------------------------------------------------------
@FAST_HASHERS
class GeneratorTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("generate_demo_data", *args, stdout=out)
        return out.getvalue()

    def test_vehicles_are_created_once_and_rules_match(self):
        self.assertIn("100 created", self.run_command("--only", "vehicles"))
        self.assertEqual(Vehicle.objects.count(), 100)
        self.assertIn("0 created, 100 already existed", self.run_command("--only", "vehicles"))
        self.assertEqual(Vehicle.objects.count(), 100)

        expected = {
            "DEMO-MC-1001": "EXPIRED",
            "DEMO-CR-1002": "EXPIRED",
            "DEMO-MC-1003": "EXPIRED",
            "DEMO-CN-1004": "INVALID",
            "DEMO-CR-1005": "UNVERIFIED",
            "DEMO-MC-1006": "INVALID",
            "DEMO-PK-1007": "VALID",
        }
        for number, category in expected.items():
            with self.subTest(number=number):
                vehicle = Vehicle.objects.get(registration_number=number)
                self.assertEqual(check_vehicle(vehicle).category, category)

        all_numbers = list(Vehicle.objects.values_list("registration_number", flat=True))
        self.assertEqual(len(all_numbers), len(set(all_numbers)))
        self.assertTrue(all(n.startswith("DEMO-") for n in all_numbers))

    def test_drivers_and_licences_are_created_once_and_rules_match(self):
        self.assertIn("100 created", self.run_command("--only", "drivers"))
        self.assertEqual(Driver.objects.count(), 100)
        self.assertEqual(DrivingLicence.objects.count(), 100)
        self.assertIn("0 created, 100 already existed", self.run_command("--only", "drivers"))
        self.assertEqual(DrivingLicence.objects.count(), 100)

        expected = {
            "DEMO-DL-100001": "EXPIRED",
            "DEMO-DL-100002": "INVALID",
            "DEMO-DL-100003": "INVALID",
            "DEMO-DL-100004": "VALID",
        }
        for number, category in expected.items():
            with self.subTest(number=number):
                licence = DrivingLicence.objects.get(licence_number=number)
                self.assertEqual(check_licence(licence).category, category)

    def test_police_records_codes_and_registration(self):
        cache.clear()
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            self.run_command("--only", "police")
            self.assertEqual(PoliceRecord.objects.count(), 100)
            self.assertEqual(PoliceRecord.objects.filter(is_eligible=False).count(), 5)
            self.assertEqual(PoliceRecord.objects.filter(claimed_by__isnull=False).count(), 0)

            codes_file = Path(tmp) / "demo_output" / "police_registration_codes.csv"
            self.assertTrue(codes_file.exists())
            with open(codes_file, newline="", encoding="utf-8") as f:
                rows = {r["demo_police_id"]: r for r in csv.DictReader(f)}
            self.assertEqual(len(rows), 100)

            # Codes are random and unique, and only hashes are stored in the database.
            codes = [r["registration_code"] for r in rows.values()]
            self.assertEqual(len(set(codes)), 100)
            for record in PoliceRecord.objects.all()[:5]:
                self.assertNotIn(rows[record.demo_police_id]["registration_code"], record.registration_code_hash)

            # A generated ID + code really registers.
            first = rows["DEMO-P-0001"]
            resp = self.client.post(
                reverse("accounts:register"),
                {"police_id": first["demo_police_id"], "registration_code": first["registration_code"]},
            )
            self.assertRedirects(resp, reverse("accounts:register_account"))

            # A disabled record is refused.
            disabled = rows["DEMO-P-0020"]
            resp = Client().post(
                reverse("accounts:register"),
                {"police_id": disabled["demo_police_id"], "registration_code": disabled["registration_code"]},
            )
            self.assertContains(resp, "This demo record is disabled")

            # Running again changes nothing.
            self.assertIn("0 created, 100 already existed", self.run_command("--only", "police"))
            self.assertEqual(PoliceRecord.objects.count(), 100)

    def test_reset_recreates_data(self):
        self.run_command("--only", "vehicles")
        self.run_command("--only", "vehicles", "--reset", "--yes")
        self.assertEqual(Vehicle.objects.count(), 100)