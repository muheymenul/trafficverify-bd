from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.testutils import FAST_HASHERS, make_admin, make_officer, make_vehicle
from verification.models import VerificationLog
from verification.services import check_vehicle

from .models import Vehicle

VT = Vehicle.VehicleType


def docs(outcome):
    return {d.name: d for d in outcome.documents}


# ---------------------------------------------------------------
# Status rules (no web page involved)
# ---------------------------------------------------------------
class VehicleRuleTests(TestCase):
    def test_all_valid(self):
        outcome = check_vehicle(make_vehicle())
        self.assertEqual(outcome.category, "VALID")
        self.assertEqual({d.status for d in outcome.documents}, {"VALID"})

    def test_expired_document_is_never_valid(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        outcome = check_vehicle(make_vehicle(tax_token_expiry=yesterday))
        self.assertEqual(outcome.category, "EXPIRED")
        self.assertEqual(docs(outcome)["Tax token"].status, "EXPIRED")
        self.assertEqual(docs(outcome)["Insurance"].status, "VALID")
        self.assertTrue(any("expired" in r.lower() for r in outcome.reasons))

    def test_expiry_day_itself_is_valid_next_day_is_expired(self):
        vehicle = make_vehicle(
            tax_token_expiry=date(2030, 6, 30),
            fitness_expiry=date(2031, 1, 1),
            insurance_expiry=date(2031, 1, 1),
        )
        self.assertEqual(check_vehicle(vehicle, today=date(2030, 6, 30)).category, "VALID")
        self.assertEqual(check_vehicle(vehicle, today=date(2030, 7, 1)).category, "EXPIRED")

    def test_motorcycle_does_not_need_fitness(self):
        bike = make_vehicle("DEMO-MC-1001", VT.MOTORCYCLE, fitness_expiry=None)
        outcome = check_vehicle(bike)
        self.assertEqual(outcome.category, "VALID")
        self.assertEqual(docs(outcome)["Fitness certificate"].status, "NOT_REQUIRED")

    def test_car_without_fitness_date_is_unverified(self):
        outcome = check_vehicle(make_vehicle(fitness_expiry=None))
        self.assertEqual(outcome.category, "UNVERIFIED")
        self.assertEqual(docs(outcome)["Fitness certificate"].status, "UNVERIFIED")

    def test_bus_needs_all_three_documents(self):
        bus = make_vehicle("DEMO-BS-1001", VT.BUS, insurance_expiry=None)
        self.assertEqual(check_vehicle(bus).category, "UNVERIFIED")

    def test_suspended_and_cancelled_are_invalid(self):
        for index, status in enumerate(["SUSPENDED", "CANCELLED"]):
            with self.subTest(status=status):
                vehicle = make_vehicle(f"DEMO-CR-20{index}1", registration_status=status)
                self.assertEqual(check_vehicle(vehicle).category, "INVALID")

    def test_invalid_beats_expired(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        vehicle = make_vehicle(registration_status="SUSPENDED", tax_token_expiry=yesterday)
        self.assertEqual(check_vehicle(vehicle).category, "INVALID")

    def test_inactive_record_is_unverified(self):
        vehicle = make_vehicle(record_status="INACTIVE")
        self.assertEqual(check_vehicle(vehicle).category, "UNVERIFIED")

    def test_expiring_soon_flag(self):
        soon = timezone.localdate() + timedelta(days=10)
        outcome = check_vehicle(make_vehicle(tax_token_expiry=soon))
        self.assertTrue(docs(outcome)["Tax token"].expiring_soon)
        self.assertFalse(docs(outcome)["Insurance"].expiring_soon)

    def test_registration_number_is_normalised(self):
        vehicle = make_vehicle(" demo-cr-7777 ")
        self.assertEqual(vehicle.registration_number, "DEMO-CR-7777")


# ---------------------------------------------------------------
# Search page
# ---------------------------------------------------------------
@FAST_HASHERS
class VehicleSearchViewTests(TestCase):
    def setUp(self):
        self.user = make_officer()
        self.client.force_login(self.user)
        self.url = reverse("vehicles:search")

    def search(self, identifier):
        return self.client.post(self.url, {"identifier": identifier})

    def test_anonymous_is_sent_to_login_and_nothing_is_logged(self):
        anon = Client()
        resp = anon.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(reverse("accounts:login")))
        resp = anon.post(self.url, {"identifier": "DEMO-CR-1001"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(VerificationLog.objects.count(), 0)

    def test_opening_the_page_does_not_search_or_log(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(VerificationLog.objects.count(), 0)

    def test_matching_record_is_shown(self):
        make_vehicle()
        resp = self.search("DEMO-CR-1001")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Demo Owner")
        self.assertContains(resp, "DEMO DATA")
        self.assertEqual(resp.context["outcome"].category, "VALID")

    def test_search_is_case_and_space_tolerant(self):
        make_vehicle()
        resp = self.search("  demo-cr-1001 ")
        self.assertIsNotNone(resp.context["vehicle"])

    def test_no_record_found(self):
        resp = self.search("DEMO-ZZ-9999")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No record found in the demo database.")
        self.assertIsNone(resp.context["vehicle"])
        self.assertEqual(VerificationLog.objects.get().result_category, "NOT_FOUND")

    def test_expired_document_is_reported(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        make_vehicle(tax_token_expiry=yesterday)
        resp = self.search("DEMO-CR-1001")
        self.assertEqual(resp.context["outcome"].category, "EXPIRED")
        self.assertContains(resp, "Expired")
        self.assertNotEqual(resp.context["log"].result_category, "VALID")

    def test_log_is_created_with_correct_values(self):
        make_vehicle()
        self.search("demo-cr-1001")
        log = VerificationLog.objects.get()
        self.assertEqual(log.officer, self.user)
        self.assertEqual(log.verification_type, "VEHICLE")
        self.assertEqual(log.searched_identifier, "DEMO-CR-1001")
        self.assertEqual(log.result_category, "VALID")

    def test_every_search_creates_a_log(self):
        make_vehicle()
        self.search("DEMO-CR-1001")
        self.search("DEMO-CR-1001")
        self.assertEqual(VerificationLog.objects.count(), 2)

    def test_bad_input_is_rejected_and_not_logged(self):
        make_vehicle()
        for text in ["ab", "DEMO@123", "' OR 1=1 --", "<script>", "X" * 25, "DEMO-CR-1001-99999999-X"]:
            with self.subTest(text=text):
                resp = self.search(text)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.context["form"].errors)
        self.assertEqual(VerificationLog.objects.count(), 0)
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_owner_name_is_escaped_against_xss(self):
        make_vehicle(owner_name="<script>alert(1)</script>")
        resp = self.search("DEMO-CR-1001")
        self.assertNotContains(resp, "<script>alert(1)</script>")
        self.assertContains(resp, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_csrf_token_is_required(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        resp = strict.post(self.url, {"identifier": "DEMO-CR-1001"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(VerificationLog.objects.count(), 0)

    def test_officer_with_disabled_record_cannot_search(self):
        from accounts.models import PoliceRecord

        PoliceRecord.objects.filter(claimed_by=self.user).update(is_eligible=False)
        self.assertEqual(self.search("DEMO-CR-1001").status_code, 403)
        self.assertEqual(VerificationLog.objects.count(), 0)

    def test_administrator_is_sent_to_admin_dashboard(self):
        admin_client = Client()
        admin_client.force_login(make_admin())
        resp = admin_client.get(self.url)
        self.assertRedirects(resp, reverse("adminpanel:home"))


# ---------------------------------------------------------------
# Officers can not change vehicle records
# ---------------------------------------------------------------
@FAST_HASHERS
class OfficerCannotModifyVehicleTests(TestCase):
    def setUp(self):
        self.user = make_officer()
        self.client.force_login(self.user)
        self.vehicle = make_vehicle()

    def test_search_form_ignores_extra_fields(self):
        self.client.post(
            reverse("vehicles:search"),
            {"identifier": "DEMO-CR-1001", "registration_status": "CANCELLED", "owner_name": "Hacker"},
        )
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.registration_status, "ACTIVE")
        self.assertEqual(self.vehicle.owner_name, "Demo Owner")

    def test_officer_can_not_edit_through_admin(self):
        resp = self.client.post(
            reverse("admin:vehicles_vehicle_change", args=[self.vehicle.pk]),
            {"owner_name": "Hacker", "registration_number": "DEMO-CR-1001", "vehicle_type": "CAR"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.owner_name, "Demo Owner")

    def test_officer_can_not_delete_through_admin(self):
        resp = self.client.post(
            reverse("admin:vehicles_vehicle_delete", args=[self.vehicle.pk]), {"post": "yes"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Vehicle.objects.filter(pk=self.vehicle.pk).exists())

    def test_officer_can_not_add_through_admin(self):
        resp = self.client.post(
            reverse("admin:vehicles_vehicle_add"),
            {"registration_number": "DEMO-CR-5555", "vehicle_type": "CAR", "owner_name": "X"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Vehicle.objects.filter(registration_number="DEMO-CR-5555").exists())