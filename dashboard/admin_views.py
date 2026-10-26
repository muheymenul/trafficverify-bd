"""
Custom Admin Dashboard (read-only pages for Administrators).

Every view is protected by @admin_required, which is checked on the server.
These pages show DEMO data only and never change any record.
"""

from datetime import date

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import admin_required
from accounts.models import PoliceRecord, User
from licences.models import DrivingLicence
from vehicles.models import Vehicle
from verification.models import VerificationLog
from verification.services import check_licence, check_vehicle

PER_PAGE = 15
Result = VerificationLog.ResultCategory

# Overall results that a vehicle / licence check can produce.
CHECK_RESULT_CHOICES = [
    (value, label) for value, label in Result.choices if value != Result.NOT_FOUND.value
]


# ---------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------
def _choice(request, name, allowed_values):
    """Return the GET value only if it is one of the allowed values."""
    value = request.GET.get(name, "")
    return value if value in allowed_values else ""


def _text(request, name, max_length=50):
    return request.GET.get(name, "").strip()[:max_length]


def _date(request, name):
    """Return a date from ?name=YYYY-MM-DD, or None if missing or invalid."""
    try:
        return date.fromisoformat(request.GET.get(name, "").strip())
    except ValueError:
        return None


def _paginate(request, queryset):
    page_obj = Paginator(queryset, PER_PAGE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)  # keep the filters when moving between pages
    return page_obj, params.urlencode()


# ---------------------------------------------------------------
# Overview
# ---------------------------------------------------------------
@admin_required
def home(request):
    today = timezone.localdate()
    logs = VerificationLog.objects.all()
    officers = User.objects.filter(role=User.Role.OFFICER)

    log_total = logs.count()
    counts = {
        row["result_category"]: row["n"]
        for row in logs.order_by().values("result_category").annotate(n=Count("id"))
    }
    breakdown = []
    for code, label in Result.choices:
        n = counts.get(code, 0)
        percent = round(n * 100 / log_total) if log_total else 0
        breakdown.append({"code": code, "label": label, "count": n, "percent": percent})

    context = {
        "officer_total": officers.count(),
        "officer_active": officers.filter(is_active=True).count(),
        "vehicle_total": Vehicle.objects.count(),
        "licence_total": DrivingLicence.objects.count(),
        "log_total": log_total,
        "log_today": logs.filter(created_at__date=today).count(),
        "police_total": PoliceRecord.objects.count(),
        "police_claimed": PoliceRecord.objects.filter(claimed_by__isnull=False).count(),
        "police_disabled": PoliceRecord.objects.filter(is_eligible=False).count(),
        "breakdown": breakdown,
        "recent_logs": logs.select_related("officer", "officer__police_profile")[:10],
        "recent_officers": officers.select_related("police_profile").order_by("-date_joined")[:5],
        "recent_vehicles": Vehicle.objects.order_by("-created_at")[:5],
        "recent_licences": DrivingLicence.objects.select_related("driver").order_by("-created_at")[:5],
    }
    return render(request, "adminpanel/home.html", context)


# ---------------------------------------------------------------
# Officers
# ---------------------------------------------------------------
@admin_required
def officers(request):
    qs = (
        User.objects.filter(role=User.Role.OFFICER)
        .select_related("police_profile")
        .annotate(log_count=Count("verification_logs"))
        .order_by("username")
    )

    q = _text(request, "q")
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(police_profile__full_name__icontains=q)
            | Q(police_profile__demo_police_id__icontains=q)
        )

    status = _choice(request, "status", ("active", "inactive"))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    page_obj, querystring = _paginate(request, qs)
    context = {
        "page_obj": page_obj,
        "querystring": querystring,
        "q": q,
        "status": status,
    }
    return render(request, "adminpanel/officers.html", context)


# ---------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------
@admin_required
def vehicles(request):
    today = timezone.localdate()
    qs = Vehicle.objects.all()

    q = _text(request, "q")
    if q:
        qs = qs.filter(Q(registration_number__icontains=q) | Q(owner_name__icontains=q))

    vehicle_type = _choice(request, "type", Vehicle.VehicleType.values)
    if vehicle_type:
        qs = qs.filter(vehicle_type=vehicle_type)

    reg_status = _choice(request, "reg", Vehicle.RegistrationStatus.values)
    if reg_status:
        qs = qs.filter(registration_status=reg_status)

    result = _choice(request, "result", [v for v, _ in CHECK_RESULT_CHOICES])
    if result:
        # The result is calculated (not stored), so we calculate it for each
        # record. This is fine for a demo with a few hundred rows.
        ids = [v.pk for v in qs if check_vehicle(v, today).category == result]
        qs = qs.filter(pk__in=ids)

    page_obj, querystring = _paginate(request, qs)

    rows = list(page_obj.object_list)
    for vehicle in rows:
        outcome = check_vehicle(vehicle, today)
        vehicle.docs = outcome.documents
        vehicle.overall = outcome.category
        vehicle.overall_label = Result(outcome.category).label
    page_obj.object_list = rows

    context = {
        "page_obj": page_obj,
        "querystring": querystring,
        "q": q,
        "selected_type": vehicle_type,
        "selected_reg": reg_status,
        "selected_result": result,
        "type_choices": Vehicle.VehicleType.choices,
        "reg_choices": Vehicle.RegistrationStatus.choices,
        "result_choices": CHECK_RESULT_CHOICES,
    }
    return render(request, "adminpanel/vehicles.html", context)


# ---------------------------------------------------------------
# Licences
# ---------------------------------------------------------------
@admin_required
def licences(request):
    today = timezone.localdate()
    qs = DrivingLicence.objects.select_related("driver")

    q = _text(request, "q")
    if q:
        qs = qs.filter(Q(licence_number__icontains=q) | Q(driver__full_name__icontains=q))

    licence_class = _choice(request, "class", DrivingLicence.LicenceClass.values)
    if licence_class:
        qs = qs.filter(licence_class=licence_class)

    status = _choice(request, "status", DrivingLicence.Status.values)
    if status:
        qs = qs.filter(status=status)

    result = _choice(request, "result", [v for v, _ in CHECK_RESULT_CHOICES])
    if result:
        ids = [l.pk for l in qs if check_licence(l, today).category == result]
        qs = qs.filter(pk__in=ids)

    page_obj, querystring = _paginate(request, qs)

    rows = list(page_obj.object_list)
    for licence in rows:
        outcome = check_licence(licence, today)
        licence.overall = outcome.category
        licence.overall_label = Result(outcome.category).label
    page_obj.object_list = rows

    context = {
        "page_obj": page_obj,
        "querystring": querystring,
        "q": q,
        "selected_class": licence_class,
        "selected_status": status,
        "selected_result": result,
        "class_choices": DrivingLicence.LicenceClass.choices,
        "status_choices": DrivingLicence.Status.choices,
        "result_choices": CHECK_RESULT_CHOICES,
    }
    return render(request, "adminpanel/licences.html", context)


# ---------------------------------------------------------------
# Verification logs (read-only audit trail)
# ---------------------------------------------------------------
@admin_required
def logs(request):
    qs = VerificationLog.objects.select_related("officer", "officer__police_profile")

    q = _text(request, "q")
    if q:
        qs = qs.filter(
            Q(officer__username__icontains=q)
            | Q(officer__police_profile__demo_police_id__icontains=q)
            | Q(searched_identifier__icontains=q)
        )

    log_type = _choice(request, "type", VerificationLog.VerificationType.values)
    if log_type:
        qs = qs.filter(verification_type=log_type)

    result = _choice(request, "result", Result.values)
    if result:
        qs = qs.filter(result_category=result)

    date_from = _date(request, "from")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = _date(request, "to")
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    page_obj, querystring = _paginate(request, qs)
    context = {
        "page_obj": page_obj,
        "querystring": querystring,
        "q": q,
        "selected_type": log_type,
        "selected_result": result,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "type_choices": VerificationLog.VerificationType.choices,
        "result_choices": Result.choices,
    }
    return render(request, "adminpanel/logs.html", context)