from django.shortcuts import render

from accounts.decorators import officer_required
from verification.forms import LicenceSearchForm
from verification.models import VerificationLog
from verification.services import check_licence, previous_check, record_verification

from .models import DrivingLicence


@officer_required
def search(request):
    """Officer searches a driving licence number (POST + CSRF)."""
    context = {"searched": None}

    if request.method == "POST":
        form = LicenceSearchForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]

            licence = (
                DrivingLicence.objects.select_related("driver")
                .filter(licence_number=identifier)
                .first()
            )

            if licence is None:
                outcome = None
                category = VerificationLog.ResultCategory.NOT_FOUND
            else:
                outcome = check_licence(licence)
                category = outcome.category

            log = record_verification(
                request.user,
                VerificationLog.VerificationType.LICENCE,
                identifier,
                category,
            )
            context.update(
                {
                    "searched": identifier,
                    "licence": licence,
                    "outcome": outcome,
                    "log": log,
                    "previous": previous_check(
                        request.user, log.verification_type, log.searched_identifier, log.pk
                    ),
                }
            )
    else:
        form = LicenceSearchForm()

    context["form"] = form
    return render(request, "licences/search.html", context)