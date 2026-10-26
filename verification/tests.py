from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from accounts.testutils import FAST_HASHERS, make_admin, make_licence, make_officer, make_vehicle

from .models import VerificationLog


def add_log(user, identifier="demo-mc-1001", vtype="VEHICLE", result="VALID"):
    return VerificationLog.objects.create(
        officer=user,
        verification_type=vtype,
        searched_identifier=identifier,
        result_category=result,
    )


@FAST_HASHERS
class AuditLogProtectionTests(TestCase):
    def setUp(self):
        self.user = make_officer()
        self.log = add_log(self.user)

    def test_identifier_is_normalised(self):
        self.assertEqual(self.log.searched_identifier, "DEMO-MC-1001")

    def test_editing_a_saved_log_is_blocked(self):
        self.log.result_category = "INVALID"
        with self.assertRaises(PermissionError):
            self.log.save()
        self.log.refresh_from_db()
        self.assertEqual(self.log.result_category, "VALID")

    def test_deleting_one_log_is_blocked(self):
        with self.assertRaises(PermissionError):
            self.log.delete()
        self.assertEqual(VerificationLog.objects.count(), 1)

    def test_queryset_update_is_blocked(self):
        with self.assertRaises(PermissionError):
            VerificationLog.objects.all().update(result_category="INVALID")
        self.log.refresh_from_db()
        self.assertEqual(self.log.result_category, "VALID")

    def test_queryset_delete_is_blocked(self):
        with self.assertRaises(PermissionError):
            VerificationLog.objects.all().delete()
        self.assertEqual(VerificationLog.objects.count(), 1)

    def test_bulk_update_is_blocked(self):
        self.log.result_category = "INVALID"
        with self.assertRaises(PermissionError):
            VerificationLog.objects.bulk_update([self.log], ["result_category"])

    def test_password_like_text_can_not_be_logged(self):
        for text in ["my secret pass!", "abcd", "A" * 21, "has space 123", "Pass$word1"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    add_log(self.user, identifier=text)
        self.assertEqual(VerificationLog.objects.count(), 1)

    def test_masked_identifier(self):
        self.assertEqual(self.log.masked_identifier, "DEMO******01")
        short = VerificationLog(searched_identifier="ABCDE")
        self.assertEqual(short.masked_identifier, "ABCDE")

    def test_officer_with_logs_can_not_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.user.delete()


@FAST_HASHERS
class AuditLogAdminTests(TestCase):
    def setUp(self):
        self.user = make_officer()
        self.log = add_log(self.user)
        self.client.force_login(make_admin())

    def test_list_and_detail_can_be_viewed(self):
        self.assertEqual(
            self.client.get(reverse("admin:verification_verificationlog_changelist")).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                reverse("admin:verification_verificationlog_change", args=[self.log.pk])
            ).status_code,
            200,
        )

    def test_add_edit_and_delete_are_forbidden_even_for_administrators(self):
        add_url = reverse("admin:verification_verificationlog_add")
        change_url = reverse("admin:verification_verificationlog_change", args=[self.log.pk])
        delete_url = reverse("admin:verification_verificationlog_delete", args=[self.log.pk])

        self.assertEqual(self.client.get(add_url).status_code, 403)
        self.assertEqual(self.client.post(change_url, {"result_category": "INVALID"}).status_code, 403)
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)

        self.log.refresh_from_db()
        self.assertEqual(self.log.result_category, "VALID")
        self.assertEqual(VerificationLog.objects.count(), 1)


@FAST_HASHERS
class HistoryCreationTests(TestCase):
    def test_searches_create_history_for_the_officer(self):
        user = make_officer()
        make_vehicle()
        make_licence()
        self.client.force_login(user)

        self.client.post(reverse("vehicles:search"), {"identifier": "DEMO-CR-1001"})
        self.client.post(reverse("licences:search"), {"identifier": "DEMO-DL-100001"})
        self.client.post(reverse("licences:search"), {"identifier": "DEMO-DL-999999"})

        self.assertEqual(VerificationLog.objects.filter(officer=user).count(), 3)

        resp = self.client.get(reverse("dashboard:history"))
        self.assertContains(resp, "DEMO******01")       # masked vehicle number
        self.assertNotContains(resp, "DEMO-CR-1001")    # full number is not shown to officers
        self.assertEqual(len(resp.context["page_obj"].object_list), 3)