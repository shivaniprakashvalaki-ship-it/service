from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.db import transaction
from django.utils import timezone

from .models import (
    Availability,
    Booking,
    Category,
    Complaint,
    ContactMessage,
    ProviderDocument,
    ProviderProfile,
    ProviderService,
    Review,
    ServiceArea,
    User,
)


class BootstrapMixin:
    """Adds Bootstrap 5 CSS classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
                css = ""
            elif isinstance(widget, forms.Select):  # includes SelectMultiple
                css = "form-select"
            else:
                css = "form-control"
            if css:
                widget.attrs["class"] = (widget.attrs.get("class", "") + " " + css).strip()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class LoginForm(BootstrapMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class StyledPasswordChangeForm(BootstrapMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(BootstrapMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapMixin, SetPasswordForm):
    pass


class CustomerRegisterForm(BootstrapMixin, UserCreationForm):
    account_role = "customer"

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "email", "phone", "city", "pincode", "address")
        labels = {"first_name": "Full name"}
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "email", "phone", "city", "pincode"):
            self.fields[name].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.username = user.email
        user.role = self.account_role
        if commit:
            user.save()
        return user


class ProviderRegisterForm(CustomerRegisterForm):
    account_role = "provider"
    field_order = [
        "first_name", "email", "phone", "city", "pincode", "locality", "address",
        "experience", "description", "categories", "base_charge", "password1", "password2",
    ]

    locality = forms.CharField(max_length=80)
    experience = forms.IntegerField(min_value=0, max_value=60, label="Experience (years)")
    description = forms.CharField(
        label="About you / skills", widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        label="Services you offer",
        help_text="Select at least one.",
    )
    base_charge = forms.DecimalField(
        min_value=1,
        max_digits=8,
        decimal_places=2,
        label="Starting charge per visit (₹)",
        help_text="Applied to each selected service; you can change it per service later.",
    )

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=True)
        cd = self.cleaned_data
        profile = ProviderProfile.objects.create(
            user=user,
            experience=cd["experience"],
            description=cd.get("description", ""),
            city=user.city,
            locality=cd["locality"],
            pincode=user.pincode,
        )
        for category in cd["categories"]:
            ProviderService.objects.create(
                provider=profile, category=category, charges=cd["base_charge"]
            )
        return user


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
class ProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "phone", "address", "city", "pincode")
        labels = {"first_name": "Full name"}
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


class ProviderContactForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "phone")
        labels = {"first_name": "Full name"}


class ProviderProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ProviderProfile
        fields = ("photo", "experience", "description", "city", "locality", "pincode")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------
class BookingForm(BootstrapMixin, forms.Form):
    booking_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), label="Date"
    )
    booking_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"), label="Preferred time"
    )
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), label="Service address")
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), required=False, label="Notes for the provider"
    )
    is_emergency = forms.BooleanField(required=False, label="This is an emergency request")

    def __init__(self, *args, service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service

    def clean(self):
        data = super().clean()
        date = data.get("booking_date")
        time = data.get("booking_time")
        if not date or not time:
            return data

        now = timezone.localtime()
        if date < now.date():
            raise forms.ValidationError("Bookings cannot be made for past dates.")
        if date == now.date() and time <= now.time():
            raise forms.ValidationError("That time has already passed today.")

        provider = self.service.provider
        if not provider.availability.exists():
            raise forms.ValidationError("This provider has not published working hours yet.")
        in_hours = provider.availability.filter(
            weekday=date.weekday(), start_time__lte=time, end_time__gt=time
        ).exists()
        if not in_hours:
            raise forms.ValidationError(
                "The provider is not available at that day/time. "
                "Check their working hours on the profile page."
            )

        probe = Booking(provider_service=self.service, booking_date=date, booking_time=time)
        if probe.has_conflict():
            raise forms.ValidationError(
                "That time slot is already taken. Please choose another time."
            )
        return data


class ReviewForm(BootstrapMixin, forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(i, f"{i} ★") for i in range(5, 0, -1)], coerce=int, label="Rating"
    )

    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}


class ComplaintForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ("booking", "subject", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["booking"].queryset = Booking.objects.filter(customer=customer)
        self.fields["booking"].required = False
        self.fields["booking"].label = "Related booking (optional)"


class ContactForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}


# ---------------------------------------------------------------------------
# Provider management forms
# ---------------------------------------------------------------------------
class ServiceForm(BootstrapMixin, forms.Form):
    category = forms.ModelChoiceField(queryset=Category.objects.filter(is_active=True))
    charges = forms.DecimalField(
        min_value=1, max_digits=8, decimal_places=2, label="Charges per visit (₹)"
    )
    description = forms.CharField(max_length=255, required=False, label="Short description")


class AreaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ServiceArea
        fields = ("city", "locality", "pincode")


class AvailabilityForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Availability
        fields = ("weekday", "start_time", "end_time")
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }


class DocumentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ProviderDocument
        fields = ("document_type", "file")
