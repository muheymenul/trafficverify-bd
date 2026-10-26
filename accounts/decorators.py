from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def officer_required(view_func):
    """
    Allow only logged-in police officers with an eligible demo police record.
    - Not logged in      -> sent to the login page
    - Administrator      -> sent to the Admin Dashboard
    - Anyone else        -> 403 Forbidden
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if user.role == "ADMIN":
            return redirect("adminpanel:home")

        profile = getattr(user, "police_profile", None)
        if user.role != "OFFICER" or profile is None or not profile.is_eligible:
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """
    Allow only active Administrators (role ADMIN and staff).
    - Not logged in      -> sent to the login page
    - Police officer     -> 403 Forbidden
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not (user.is_active and user.is_staff and user.role == "ADMIN"):
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper