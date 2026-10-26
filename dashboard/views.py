from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.views import PasswordChangeView
from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator

from accounts.decorators import officer_required
from verification.models import VerificationLog

from .forms import StyledPasswordChangeForm


def _my_logs(user):
    """Only the logs that belong to this officer (never anyone else's)."""
    return VerificationLog.objects.filter(officer=user)


@officer_required
def home(request):
    """Officer dashboard."""
    profile = request.user.police_profile
    logs = _my_logs(request.user)

    context = {
        "profile": profile,
        "total_count": logs.count(),
        "today_count": logs.filter(created_at__date=timezone.localdate()).count(),
        "last_log": logs.first(),
        "recent_logs": logs[:5],
    }
    return render(request, "dashboard/home.html", context)


@officer_required
def history(request):
    """The officer's own verification history, with filters and pages."""
    logs = _my_logs(request.user)

    # Accept only values that really exist in our choices.
    selected_type = request.GET.get("type", "")
    if selected_type in VerificationLog.VerificationType.values:
        logs = logs.filter(verification_type=selected_type)
    else:
        selected_type = ""

    selected_result = request.GET.get("result", "")
    if selected_result in VerificationLog.ResultCategory.values:
        logs = logs.filter(result_category=selected_result)
    else:
        selected_result = ""

    page_obj = Paginator(logs, 10).get_page(request.GET.get("page"))

    # Keep the filters when moving between pages.
    params = request.GET.copy()
    params.pop("page", None)

    context = {
        "page_obj": page_obj,
        "selected_type": selected_type,
        "selected_result": selected_result,
        "type_choices": VerificationLog.VerificationType.choices,
        "result_choices": VerificationLog.ResultCategory.choices,
        "querystring": params.urlencode(),
    }
    return render(request, "dashboard/history.html", context)


@officer_required
def account_settings(request):
    """Shows the officer's own account information (read only)."""
    return render(
        request,
        "dashboard/settings.html",
        {"profile": request.user.police_profile},
    )


@method_decorator(officer_required, name="dispatch")
class OfficerPasswordChangeView(SuccessMessageMixin, PasswordChangeView):
    template_name = "dashboard/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("dashboard:settings")
    success_message = "Your password was changed successfully."