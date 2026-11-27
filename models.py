from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.mail import send_mail
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.db.models import Avg, Count
from django.utils import timezone

# ---------------------------------------------------------------------------
# Business-rule constants (change here, rules update everywhere)
# ---------------------------------------------------------------------------
SLOT_MINUTES = 60  # a confirmed job blocks the provider for this long
CANCEL_HOURS = 2  # accepted bookings can be cancelled only this many hours before start

PHONE_VALIDATOR = RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")
PINCODE_VALIDATOR = RegexValidator(r"^\d{6}$", "Enter a valid 6-digit PIN code.")


def validate_document_size(f):
    if f.size > 5 * 1024 * 1024:
        raise ValidationError("File must be 5 MB or smaller.")


def validate_photo_size(f):
    if f.size > 2 * 1024 * 1024:
        raise ValidationError("Photo must be 2 MB or smaller.")


def public_storage():
    """Provider photos: public Supabase bucket (or MEDIA_ROOT when USE_SUPABASE=0)."""
    if settings.SUPABASE_ENABLED:
        from supabase_storage import SupabaseStorage

        return SupabaseStorage(
            settings.SUPABASE_PUBLIC_BUCKET, True, settings.SUPABASE_URL, settings.SUPABASE_KEY
        )
    return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)


def private_storage():
    """Verification documents: PRIVATE Supabase bucket, never publicly URL-addressable
    (or PRIVATE_MEDIA_ROOT when USE_SUPABASE=0)."""
    if settings.SUPABASE_ENABLED:
        from supabase_storage import SupabaseStorage

        return SupabaseStorage(
            settings.SUPABASE_PRIVATE_BUCKET, False, settings.SUPABASE_URL, settings.SUPABASE_KEY
        )
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ("customer", "Customer"),
        ("provider", "Service Provider"),
        ("admin", "Administrator"),
    )
    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="customer")
    phone = models.CharField(max_length=10, blank=True, validators=[PHONE_VALIDATOR])
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=6, blank=True, validators=[PINCODE_VALIDATOR])

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = "admin"
        if self.role == "admin":
            self.is_staff = True
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.username


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=255, blank=True)
    icon = models.CharField(
        max_length=40, default="bi-tools", help_text="Bootstrap Icons class, e.g. bi-wrench"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class ProviderProfile(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="provider_profile")
    photo = models.ImageField(
        upload_to="photos/",
        storage=public_storage,
        blank=True,
        null=True,
        validators=[validate_photo_size],
    )
    experience = models.PositiveSmallIntegerField(
        "Experience (years)", default=0, validators=[MaxValueValidator(60)]
    )
    description = models.TextField("About / skills", blank=True)
    city = models.CharField(max_length=80)
    locality = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6, validators=[PINCODE_VALIDATOR])
    verification_status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="pending"
    )
    admin_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.user.display_name

    @property
    def is_approved(self):
        return self.verification_status == "approved"

    @property
    def badge(self):
        return {"pending": "warning", "approved": "success", "rejected": "danger"}[
            self.verification_status
        ]

    def rating_summary(self):
        """(average rating or None, number of visible reviews)"""
        agg = self.reviews.filter(is_hidden=False).aggregate(avg=Avg("rating"), n=Count("id"))
        return agg["avg"], agg["n"]


class ProviderService(models.Model):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="services")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="provider_services")
    charges = models.DecimalField(
        "Charges per visit (₹)",
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1"))],
    )
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("provider", "category")
        ordering = ["category__name"]

    def __str__(self):
        return f"{self.category.name} by {self.provider}"


class ServiceArea(models.Model):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="areas")
    city = models.CharField(max_length=80)
    locality = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6, validators=[PINCODE_VALIDATOR])

    def __str__(self):
        return f"{self.locality}, {self.city} {self.pincode}"


class Availability(models.Model):
    WEEKDAYS = (
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    )
    provider = models.ForeignKey(
        ProviderProfile, on_delete=models.CASCADE, related_name="availability"
    )
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name_plural = "availability"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class ProviderDocument(models.Model):
    TYPE_CHOICES = (
        ("id_proof", "Identity proof"),
        ("address_proof", "Address proof"),
        ("skill_certificate", "Skill / training certificate"),
        ("other", "Other"),
    )
    STATUS_CHOICES = (("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"))
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    file = models.FileField(
        upload_to="documents/",
        storage=private_storage,
        validators=[
            FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]),
            validate_document_size,
        ],
        help_text="PDF, JPG or PNG, max 5 MB.",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.provider}"


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
class Booking(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    )
    # Allowed status transitions. Anything not listed is a terminal state.
    TRANSITIONS = {
        "pending": ["accepted", "rejected", "cancelled"],
        "accepted": ["in_progress", "cancelled"],
        "in_progress": ["completed"],
    }
    BADGES = {
        "pending": "warning",
        "accepted": "info",
        "in_progress": "primary",
        "completed": "success",
        "rejected": "danger",
        "cancelled": "secondary",
    }

    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    provider_service = models.ForeignKey(
        ProviderService, on_delete=models.PROTECT, related_name="bookings"
    )
    booking_date = models.DateField()
    booking_time = models.TimeField()
    address = models.TextField()
    notes = models.TextField(blank=True)
    is_emergency = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    amount = models.DecimalField(max_digits=8, decimal_places=2)  # price snapshot at booking time
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-booking_date", "-booking_time"]

    def __str__(self):
        return f"#{self.pk} {self.provider_service.category.name} on {self.booking_date}"

    @property
    def provider(self):
        return self.provider_service.provider

    @property
    def badge(self):
        return self.BADGES.get(self.status, "secondary")

    @property
    def has_review(self):
        return Review.objects.filter(booking=self).exists()

    @property
    def starts_at(self):
        return timezone.make_aware(datetime.combine(self.booking_date, self.booking_time))

    def can_cancel(self):
        if self.status == "pending":
            return True
        if self.status == "accepted":
            return self.starts_at - timezone.now() >= timedelta(hours=CANCEL_HOURS)
        return False

    def has_conflict(self):
        """True if the provider already has a confirmed job overlapping this slot."""
        others = Booking.objects.filter(
            provider_service__provider=self.provider_service.provider,
            booking_date=self.booking_date,
            status__in=("accepted", "in_progress"),
        )
        if self.pk:
            others = others.exclude(pk=self.pk)
        mine = datetime.combine(self.booking_date, self.booking_time)
        for other in others:
            theirs = datetime.combine(other.booking_date, other.booking_time)
            if abs(mine - theirs) < timedelta(minutes=SLOT_MINUTES):
                return True
        return False


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews_given")
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    is_hidden = models.BooleanField(default=False, help_text="Hide inappropriate reviews")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating}/5 for {self.provider}"


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.message[:40]}"


def notify(user, message, link=""):
    """Create an in-app notification and send an email copy (console backend in development)."""
    Notification.objects.create(user=user, message=message[:255], link=link)
    if user.email:
        send_mail(
            "HomeServe update",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )


class Favourite(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favourites")
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="fans")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("customer", "provider")
        ordering = ["-created_at"]


class Complaint(models.Model):
    STATUS_CHOICES = (("open", "Open"), ("in_review", "In review"), ("resolved", "Resolved"))
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="complaints")
    provider = models.ForeignKey(
        ProviderProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints"
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints"
    )
    subject = models.CharField(max_length=120)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    admin_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=150)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.email})"
