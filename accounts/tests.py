import re

from django.contrib.admin.sites import site
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .admin import UserAdmin
from .forms import GENERIC_ERROR
from .models import PoliceRecord, User
from .testutils import (
    CODE,
    FAST_HASHERS,
    PASSWORD,
    make_admin,
    make_officer,
    make_police_record,
)

SESSION_KEY = "registration_record_id"


# ---------------------------------------------------------------
# Police record model
# ---------------------------------------------------------------
@FAST_HASHERS
class PoliceRecordModelTests(TestCase):
    def test_code_is_hashed_not_plain(self):
        record = make_police_record()
        self.assertNotIn(CODE, record.registration_code_hash)
        self.assertTrue(record.check_registration_code(CODE))
        self.assertFalse(record.check_registration_code("wrong-code"))

    def test_record_without_code_never_matches(self):
        record = PoliceRecord.objects.create(
            demo_police_id="DEMO-P-0007",
            full_name="No Code",
            rank=PoliceRecord.Rank.ASI,
            unit="Demo Unit",
        )
        self.assertFalse(record.check_registration_code(""))
        self.assertFalse(record.check_registration_code("anything"))

    def test_police_id_is_normalised(self):
        record = make_police_record(" demo-p-0005 ")
        self.assertEqual(record.demo_police_id, "DEMO-P-0005")

    def test_police_id_must_be_unique(self):
        make_police_record("DEMO-P-0001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_police_record("DEMO-P-0001")

    def test_one_user_cannot_claim_two_records(self):
        user = make_officer()
        second = make_police_record("DEMO-P-0002")
        second.claimed_by = user
        with self.assertRaises(IntegrityError), transaction.atomic():
            second.save()


# ---------------------------------------------------------------
# Registration
# ---------------------------------------------------------------
@FAST_HASHERS
class RegistrationTests(TestCase):
    def setUp(self):
        cache.clear()  # the failed-attempt counter lives in the cache
        self.record = make_police_record()
        self.url = reverse("accounts:register")
        self.url2 = reverse("accounts:register_account")

    def start(self, client, police_id="DEMO-P-0001", code=CODE):
        return client.post(self.url, {"police_id": police_id, "registration_code": code})

    def finish(self, client, username="new_officer", email="new@example.com", password=PASSWORD):
        return client.post(
            self.url2,
            {"username": username, "email": email, "password1": password, "password2": password},
        )

    def test_valid_registration_full_flow(self):
        resp = self.start(self.client, police_id="demo-p-0001")  # lower case is accepted
        self.assertRedirects(resp, self.url2)

        resp = self.client.get(self.url2)
        self.assertContains(resp, "Test Officer")
        self.assertContains(resp, "Sub-Inspector")

        resp = self.finish(self.client)
        self.assertRedirects(resp, reverse("accounts:login"))

        user = User.objects.get(username="new_officer")
        self.assertEqual(user.role, User.Role.OFFICER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotIn(PASSWORD, user.password)  # stored hashed

        self.record.refresh_from_db()
        self.assertEqual(self.record.claimed_by, user)
        self.assertIsNotNone(self.record.claimed_at)

    def test_unknown_police_id_rejected(self):
        resp = self.start(self.client, police_id="DEMO-P-5555")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, GENERIC_ERROR)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_wrong_code_rejected(self):
        resp = self.start(self.client, code="wrong-code")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, GENERIC_ERROR)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_unknown_id_and_wrong_code_give_same_message(self):
        a = self.start(Client(), police_id="DEMO-P-5555")
        b = self.start(Client(), code="wrong-code")
        self.assertEqual(
            list(a.context["form"].non_field_errors()),
            list(b.context["form"].non_field_errors()),
        )

    def test_disabled_record_rejected_with_correct_code(self):
        PoliceRecord.objects.filter(pk=self.record.pk).update(is_eligible=False)
        resp = self.start(self.client)
        self.assertContains(resp, "This demo record is disabled")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_disabled_record_not_revealed_with_wrong_code(self):
        PoliceRecord.objects.filter(pk=self.record.pk).update(is_eligible=False)
        resp = self.start(self.client, code="wrong-code")
        self.assertContains(resp, GENERIC_ERROR)
        self.assertNotContains(resp, "This demo record is disabled")

    def test_duplicate_registration_rejected(self):
        self.start(self.client)
        self.finish(self.client)

        resp = self.start(Client())  # a different visitor, same ID and code
        self.assertContains(resp, "already been registered")
        self.assertEqual(User.objects.count(), 1)

    def test_step2_needs_step1(self):
        resp = self.client.get(self.url2)
        self.assertRedirects(resp, self.url)

        resp = self.finish(self.client)  # posting directly, without step 1
        self.assertRedirects(resp, self.url)
        self.assertEqual(User.objects.count(), 0)

    def test_record_disabled_between_steps(self):
        self.start(self.client)
        PoliceRecord.objects.filter(pk=self.record.pk).update(is_eligible=False)
        resp = self.finish(self.client)
        self.assertRedirects(resp, self.url)
        self.assertEqual(User.objects.count(), 0)

    def test_record_claimed_by_someone_else_between_steps(self):
        self.start(self.client)
        other = User.objects.create_user("someone", password=PASSWORD)
        PoliceRecord.objects.filter(pk=self.record.pk).update(claimed_by=other)
        resp = self.finish(self.client)
        self.assertRedirects(resp, self.url)
        self.assertEqual(User.objects.filter(username="new_officer").count(), 0)

    def test_duplicate_email_rejected(self):
        make_officer(username="first", police_id="DEMO-P-0002")
        self.start(self.client)
        resp = self.finish(self.client, email="first@example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["form"].errors)
        self.assertFalse(User.objects.filter(username="new_officer").exists())

    def test_weak_password_rejected(self):
        self.start(self.client)
        resp = self.finish(self.client, password="12345678")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="new_officer").exists())

    def test_too_many_failed_attempts_block_registration(self):
        for _ in range(10):
            self.start(self.client, code="wrong-code")
        resp = self.start(self.client)  # even the CORRECT code is refused now
        self.assertContains(resp, "Too many failed attempts")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_logged_in_user_is_sent_away_from_register(self):
        user = make_officer(username="already", police_id="DEMO-P-0003")
        self.client.force_login(user)
        self.assertRedirects(self.client.get(self.url), reverse("dashboard:home"))


# ---------------------------------------------------------------
# Login and logout
# ---------------------------------------------------------------
@FAST_HASHERS
class LoginLogoutTests(TestCase):
    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.logout_url = reverse("accounts:logout")

    def login(self, username="officer1", password=PASSWORD):
        return self.client.post(self.login_url, {"username": username, "password": password})

    def test_officer_login_success(self):
        make_officer()
        resp = self.login()
        self.assertRedirects(resp, reverse("dashboard:home"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_fails(self):
        make_officer()
        resp = self.login(password="wrong-password")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_user_fails(self):
        resp = self.login(username="nobody")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_account_cannot_login(self):
        user = make_officer()
        user.is_active = False
        user.save()
        self.login()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_officer_with_disabled_record_cannot_login(self):
        make_officer(is_eligible=False)
        resp = self.login()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_officer_without_record_cannot_login(self):
        User.objects.create_user("lonely", password=PASSWORD, role=User.Role.OFFICER)
        self.login(username="lonely")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_record_disabled_after_login_blocks_pages(self):
        user = make_officer()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)
        PoliceRecord.objects.filter(claimed_by=user).update(is_eligible=False)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)

    def test_administrator_goes_to_admin_dashboard(self):
        make_admin()
        resp = self.login(username="admin1")
        self.assertRedirects(resp, reverse("adminpanel:home"))

    def test_logout_needs_post(self):
        self.client.force_login(make_officer())
        self.assertEqual(self.client.get(self.logout_url).status_code, 405)

    def test_logout_ends_session(self):
        self.client.force_login(make_officer())
        resp = self.client.post(self.logout_url)
        self.assertRedirects(resp, self.login_url)
        self.assertNotIn("_auth_user_id", self.client.session)
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 302)

    def test_session_cookie_settings(self):
        from django.conf import settings

        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 7200)


# ---------------------------------------------------------------
# Password reset (emails go to the test outbox, nothing is really sent)
# ---------------------------------------------------------------
@FAST_HASHERS
class PasswordResetTests(TestCase):
    NEW_PASSWORD = "An0ther-Str0ng-Pass-88"

    def setUp(self):
        self.user = make_officer()
        self.url = reverse("accounts:password_reset")

    def request_link(self):
        resp = self.client.post(self.url, {"email": "officer1@example.com"})
        self.assertRedirects(resp, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"http://testserver(/password-reset/\S+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_full_reset_flow(self):
        link = self.request_link()
        resp = self.client.get(link, follow=True)
        self.assertEqual(resp.status_code, 200)
        final_url = resp.redirect_chain[-1][0]

        resp = self.client.post(
            final_url,
            {"new_password1": self.NEW_PASSWORD, "new_password2": self.NEW_PASSWORD},
        )
        self.assertRedirects(resp, reverse("accounts:password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))

    def test_link_works_only_once(self):
        link = self.request_link()
        resp = self.client.get(link, follow=True)
        final_url = resp.redirect_chain[-1][0]
        self.client.post(
            final_url,
            {"new_password1": self.NEW_PASSWORD, "new_password2": self.NEW_PASSWORD},
        )
        resp = Client().get(link, follow=True)
        self.assertContains(resp, "Link not valid")

    def test_unknown_email_sends_nothing_but_looks_the_same(self):
        resp = self.client.post(self.url, {"email": "nobody@example.com"})
        self.assertRedirects(resp, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_garbage_link_is_rejected(self):
        resp = self.client.get(
            reverse("accounts:password_reset_confirm", args=["abc", "bad-token"]), follow=True
        )
        self.assertContains(resp, "Link not valid")


# ---------------------------------------------------------------
# Roles: Administrator and Police Officer
# ---------------------------------------------------------------
ADMIN_URL_NAMES = [
    "admin:index",
    "admin:vehicles_vehicle_changelist",
    "admin:licences_driver_changelist",
    "admin:licences_drivinglicence_changelist",
    "admin:accounts_user_changelist",
    "admin:accounts_policerecord_changelist",
    "admin:verification_verificationlog_changelist",
]


@FAST_HASHERS
class RoleAccessTests(TestCase):
    def test_superuser_is_always_administrator(self):
        admin = make_admin()
        self.assertEqual(admin.role, User.Role.ADMINISTRATOR)
        self.assertTrue(admin.is_staff)

    def test_administrator_can_open_admin_pages(self):
        self.client.force_login(make_admin())
        for name in ADMIN_URL_NAMES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_officer_cannot_open_admin_pages(self):
        self.client.force_login(make_officer())
        for name in ADMIN_URL_NAMES:
            with self.subTest(page=name):
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 302)
                self.assertIn("/admin/login/", resp["Location"])

    def test_anonymous_cannot_open_admin_pages(self):
        for name in ADMIN_URL_NAMES:
            with self.subTest(page=name):
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 302)
                self.assertIn("/admin/login/", resp["Location"])

    def test_staff_flag_alone_does_not_make_an_officer_an_administrator(self):
        # An officer account that somehow has is_staff set still can not use the
        # custom Admin Dashboard (it checks the ADMIN role on the server).
        user = make_officer()
        User.objects.filter(pk=user.pk).update(is_staff=True)
        self.client.force_login(User.objects.get(pk=user.pk))
        self.assertEqual(self.client.get(reverse("adminpanel:home")).status_code, 403)

    def test_admin_form_forces_staff_off_for_officers(self):
        model_admin = UserAdmin(User, site)
        sneaky = User(username="sneaky", role=User.Role.OFFICER, is_staff=True)
        model_admin.save_model(None, sneaky, None, False)
        sneaky.refresh_from_db()
        self.assertFalse(sneaky.is_staff)
        self.assertFalse(sneaky.is_superuser)
        self.assertEqual(sneaky.role, User.Role.OFFICER)

    def test_admin_form_gives_administrators_staff_access(self):
        model_admin = UserAdmin(User, site)
        boss = User(username="boss", role=User.Role.ADMINISTRATOR)
        model_admin.save_model(None, boss, None, False)
        boss.refresh_from_db()
        self.assertTrue(boss.is_staff)
        self.assertEqual(boss.role, User.Role.ADMINISTRATOR)