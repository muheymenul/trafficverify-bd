from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.testutils import FAST_HASHERS, make_officer, make_licence
from verification.models import VerificationLog
from verification.services import check_licence

from .models import DrivingLicence


# ---------------------------------------------------------------
# Status rules
# ---------------------------------------------------------------
class LicenceRuleTests(TestCase):
    def test_active_and_not_expired_is_valid(self):
        self.assertEqual(check_licence(make_licence()).category, "VALID")

    def test_expired_licence(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        outcome = check_licence(make_licence(expiry_date=yesterday))
        self.assertEqual(outcome.category, "EXPIRED")
        self.assertTrue(any("expired" in r.lower() for r in outcome.reasons))

    def test_expiry_day_itself_is_valid_next_day_is_expired(self):
        licence = make_licence(
            issue_date=date(2025, 6, 30), expiry_date=date(2030, 6, 30)
        )
        self.assertEqual(check_licence(licence, today=date(2030, 6, 30)).category, "VALID")
        self.assertEqual(check_licence(licence, today=date(2030, 7, 1)).category, "EXPIRED")

    def test_suspended_and_revoked_are_invalid_even_if_not_expired(self):
        for index, status in enumerate(["SUSPENDED", "REVOKED"]):
            with self.subTest(status=status):
                licence = make_licence(f"DEMO-DL-20000{index}", status=status)
                self.assertEqual(check_licence(licence).category, "INVALID")

    def test_invalid_beats_expired(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        licence = make_licence(status="SUSPENDED", expiry_date=yesterday)
        self.assertEqual(check_licence(licence).category, "INVALID")

    def test_expiry_must_be_after_issue_date(self):
        from django.core.exceptions import ValidationError

        licence = make_licence()
        licence.expiry_date = licence.issue_date
        with self.assertRaises(ValidationError):
            licence.clean()


# ---------------------------------------------------------------
# Search page
# ---------------------------------------------------------------
@FAST_HASHERS
class LicenceSearchViewTests(TestCase):
    def setUp(self):
        self.user = make_officer()
        self.client.force_login(self.user)
        self.url = reverse("licences:search")

    def search(self, identifier):
        return self.client.post(self.url, {"identifier": identifier})

    def test_anonymous_is_sent_to_login(self):
        resp = Client().post(self.url, {"identifier": "DEMO-DL-100001"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(reverse("accounts:login")))
        self.assertEqual(VerificationLog.objects.count(), 0)

    def test_matching_licence_is_shown(self):
        make_licence()
        resp = self.search("DEMO-DL-100001")
        self.assertContains(resp, "Demo Driver")
        self.assertContains(resp, "DEMO DATA")
        self.assertEqual(resp.context["outcome"].category, "VALID")

    def test_date_of_birth_is_not_shown(self):
        make_licence()  # driver born 1971-02-03
        resp = self.search("DEMO-DL-100001")
        self.assertNotContains(resp, "1971")
        self.assertNotContains(resp, "Date of birth")

    def test_no_record_found(self):
        resp = self.search("DEMO-DL-999999")
        self.assertContains(resp, "No record found in the demo database.")
        self.assertEqual(VerificationLog.objects.get().result_category, "NOT_FOUND")

    def test_expired_licence_is_reported(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        make_licence(expiry_date=yesterday)
        resp = self.search("DEMO-DL-100001")
        self.assertEqual(resp.context["outcome"].category, "EXPIRED")
        self.assertContains(resp, "Expired")

    def test_suspended_licence_is_invalid(self):
        make_licence(status="SUSPENDED")
        resp = self.search("DEMO-DL-100001")
        self.assertEqual(resp.context["outcome"].category, "INVALID")

    def test_log_is_created(self):
        make_licence()
        self.search("demo-dl-100001")
        log = VerificationLog.objects.get()
        self.assertEqual(log.officer, self.user)
        self.assertEqual(log.verification_type, "LICENCE")
        self.assertEqual(log.searched_identifier, "DEMO-DL-100001")
        self.assertEqual(log.result_category, "VALID")

    def test_bad_input_is_rejected_and_not_logged(self):
        for text in ["x", "DL;DROP TABLE", "<b>bold</b>", "DEMO-DL-100001-EXTRA-LONG-TEXT"]:
            with self.subTest(text=text):
                resp = self.search(text)
                self.assertTrue(resp.context["form"].errors)
        self.assertEqual(VerificationLog.objects.count(), 0)

    def test_officer_can_not_change_licence_through_admin(self):
        licence = make_licence()
        resp = self.client.post(
            reverse("admin:licences_drivinglicence_change", args=[licence.pk]),
            {"licence_number": "DEMO-DL-100001", "status": "REVOKED"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        licence.refresh_from_db()
        self.assertEqual(licence.status, "ACTIVE")
        resp = self.client.post(
            reverse("admin:licences_drivinglicence_delete", args=[licence.pk]), {"post": "yes"}
        )
        self.assertTrue(DrivingLicence.objects.filter(pk=licence.pk).exists())