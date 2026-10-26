import time

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import CreateAccountForm, StyledAuthenticationForm, VerifyPoliceForm
from .models import PoliceRecord

# Session keys that remember "step 1 passed"
SESSION_RECORD_KEY = "registration_record_id"
SESSION_TIME_KEY = "registration_verified_at"
VERIFIED_VALID_SECONDS = 15 * 60  # step 2 must be finished within 15 minutes

# Simple protection against guessing codes
MAX_FAILED_ATTEMPTS = 10
BLOCK_SECONDS = 15 * 60


class RecordNotAvailable(Exception):
    """The police record was disabled or claimed while the user was registering."""


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _failure_key(request):
    return f"register_failures:{request.META.get('REMOTE_ADDR', 'unknown')}"


def _is_blocked(request):
    return cache.get(_failure_key(request), 0) >= MAX_FAILED_ATTEMPTS


def _count_failure(request):
    key = _failure_key(request)
    try:
        cache.incr(key)
    except ValueError:  # key does not exist yet
        cache.set(key, 1, BLOCK_SECONDS)


def _clear_verified(request):
    request.session.pop(SESSION_RECORD_KEY, None)
    request.session.pop(SESSION_TIME_KEY, None)


def _get_verified_record(request):
    """Return the police record that passed step 1, or None."""
    record_id = request.session.get(SESSION_RECORD_KEY)
    verified_at = request.session.get(SESSION_TIME_KEY)
    if not record_id or not verified_at:
        return None
    if time.time() - verified_at > VERIFIED_VALID_SECONDS:
        _clear_verified(request)
        return None
    return PoliceRecord.objects.filter(
        pk=record_id, is_eligible=True, claimed_by__isnull=True
    ).first()


# ---------------------------------------------------------------
# Registration
# ---------------------------------------------------------------
def register_verify(request):
    """Step 1: Demo Police ID + one-time registration code."""
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        if _is_blocked(request):
            messages.error(
                request,
                "Too many failed attempts. Please wait 15 minutes and try again.",
            )
            form = VerifyPoliceForm()
        else:
            form = VerifyPoliceForm(request.POST)
            if form.is_valid():
                request.session[SESSION_RECORD_KEY] = form.record.pk
                request.session[SESSION_TIME_KEY] = time.time()
                return redirect("accounts:register_account")
            _count_failure(request)
    else:
        form = VerifyPoliceForm()

    return render(request, "accounts/register_step1.html", {"form": form})


def register_account(request):
    """Step 2: show the fictional name and rank, then create the account."""
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    record = _get_verified_record(request)
    if record is None:
        messages.error(
            request,
            "Please verify your Demo Police ID and registration code first.",
        )
        return redirect("accounts:register")

    if request.method == "POST":
        form = CreateAccountForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Lock and re-check the record at the very last moment.
                    locked = PoliceRecord.objects.select_for_update().get(pk=record.pk)
                    if not locked.is_eligible or locked.is_claimed:
                        raise RecordNotAvailable
                    user = form.save()
                    locked.claimed_by = user
                    locked.claimed_at = timezone.now()
                    locked.save(update_fields=["claimed_by", "claimed_at"])
            except RecordNotAvailable:
                _clear_verified(request)
                messages.error(
                    request,
                    "This demo record is no longer available for registration.",
                )
                return redirect("accounts:register")

            _clear_verified(request)
            messages.success(
                request,
                "Account created successfully. You can now log in.",
            )
            return redirect("accounts:login")
    else:
        form = CreateAccountForm()

    return render(
        request,
        "accounts/register_step2.html",
        {"form": form, "record": record},
    )


# ---------------------------------------------------------------
# Login
# ---------------------------------------------------------------
class OfficerLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        # Administrators go to the Admin Dashboard, officers to their dashboard.
        if self.request.user.role == "ADMIN":
            return reverse("adminpanel:home")
        return reverse("dashboard:home")