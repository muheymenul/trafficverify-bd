import re

from django import forms
from django.core.exceptions import ValidationError

from accounts.forms import BootstrapFormMixin

IDENTIFIER_PATTERN = re.compile(r"^[A-Z0-9-]{5,20}$")


class IdentifierFormBase(BootstrapFormMixin, forms.Form):
    """Shared cleaning for vehicle and licence number search boxes."""

    def clean_identifier(self):
        value = self.cleaned_data["identifier"].strip().upper().replace(" ", "")
        if not IDENTIFIER_PATTERN.match(value):
            raise ValidationError(
                "Use only letters, numbers and hyphens (5 to 20 characters)."
            )
        return value


class VehicleSearchForm(IdentifierFormBase):
    identifier = forms.CharField(
        label="Vehicle registration number",
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. DEMO-MC-1001",
                "autocomplete": "off",
                "autofocus": True,
            }
        ),
    )


class LicenceSearchForm(IdentifierFormBase):
    identifier = forms.CharField(
        label="Driving licence number",
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. DEMO-DL-100001",
                "autocomplete": "off",
                "autofocus": True,
            }
        ),
    )