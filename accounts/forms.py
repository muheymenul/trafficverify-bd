from functools import lru_cache

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError

from .models import PoliceRecord, User

# One message for "unknown ID" AND "wrong code", so outsiders can not
# find out which Demo Police IDs exist.
GENERIC_ERROR = "The Demo Police ID or registration code is incorrect."


class BootstrapFormMixin:
    """Adds the Bootstrap 'form-control' CSS class to every input."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " form-control").strip()


@lru_cache(maxsize=1)
def _dummy_hash():
    return make_password("not-a-real-code")


# ---------------------------------------------------------------
# Registration step 1: check Demo Police ID + one-time code
# ---------------------------------------------------------------
class VerifyPoliceForm(BootstrapFormMixin, forms.Form):
    police_id = forms.CharField(
        label="Demo Police ID",
        max_length=20,
        widget=forms.TextInput(
            attrs={"placeholder": "DEMO-P-0001", "autocomplete": "off"}
        ),
    )
    registration_code = forms.CharField(
        label="One-time registration code",
        max_length=64,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    record = None  # filled in when verification succeeds

    def clean_police_id(self):
        return self.cleaned_data["police_id"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        police_id = cleaned.get("police_id")
        code = cleaned.get("registration_code")
        if not police_id or not code:
            return cleaned

        record = PoliceRecord.objects.filter(demo_police_id=police_id).first()

        if record is None:
            # Do the same slow hash work, so timing does not reveal the ID is unknown.
            check_password(code.strip(), _dummy_hash())
            raise ValidationError(GENERIC_ERROR)

        if not record.check_registration_code(code):
            raise ValidationError(GENERIC_ERROR)

        # The code is correct, so now it is safe to give more detail.
        if not record.is_eligible:
            raise ValidationError(
                "This demo record is disabled. Please contact the administrator."
            )
        if record.is_claimed:
            raise ValidationError(
                "This demo record has already been registered. "
                "A record can be used only once."
            )

        self.record = record
        return cleaned


# ---------------------------------------------------------------
# Registration step 2: username, email, password
# ---------------------------------------------------------------
class CreateAccountForm(BootstrapFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].label = "Email (needed for password reset)"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already used by another account.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # A self-registered user is ALWAYS a plain police officer.
        user.role = User.Role.OFFICER
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------
# Login and password reset forms (Django's forms + Bootstrap look)
# ---------------------------------------------------------------
class StyledAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    def confirm_login_allowed(self, user):
        # Django's own check: inactive accounts can not log in.
        super().confirm_login_allowed(user)

        # Extra account status check for police officers.
        if user.role == User.Role.OFFICER:
            profile = getattr(user, "police_profile", None)
            if profile is None:
                raise ValidationError(
                    "This account is not linked to a demo police record.",
                    code="no_profile",
                )
            if not profile.is_eligible:
                raise ValidationError(
                    "Your demo police record is disabled. Contact the administrator.",
                    code="record_disabled",
                )


class StyledPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass