from django.shortcuts import render

from accounts.decorators import officer_required
from verification.forms import VehicleSearchForm
from verification.models import VerificationLog
from verification.services import check_vehicle, previous_check, record_verification

from .models import Vehicle


@officer_required
def search(request):
    """Officer searches a vehicle registration number (POST + CSRF)."""
    context = {"searched": None}

    if request.method == "POST":
        form = VehicleSearchForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]

            # Django ORM query: the value is never joined into SQL text.
            vehicle = Vehicle.objects.filter(registration_number=identifier).first()

            if vehicle is None:
                outcome = None
                category = VerificationLog.ResultCategory.NOT_FOUND
            else:
                outcome = check_vehicle(vehicle)
                category = outcome.category

            log = record_verification(
                request.user,
                VerificationLog.VerificationType.VEHICLE,
                identifier,
                category,
            )
            context.update(
                {
                    "searched": identifier,
                    "vehicle": vehicle,
                    "outcome": outcome,
                    "log": log,
                    "previous": previous_check(
                        request.user, log.verification_type, log.searched_identifier, log.pk
                    ),
                }
            )
    else:
        form = VehicleSearchForm()

    context["form"] = form
    return render(request, "vehicles/search.html", context)