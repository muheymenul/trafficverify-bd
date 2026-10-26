from django.contrib.auth.forms import PasswordChangeForm

from accounts.forms import BootstrapFormMixin


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    """Django's password change form with the Bootstrap look."""