import csv
import mimetypes
from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Avg, Count, F, Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    AreaForm,
    AvailabilityForm,
    BookingForm,
    ComplaintForm,
    ContactForm,
    CustomerRegisterForm,
    DocumentForm,
    LoginForm,
    ProfileForm,
    ProviderContactForm,
    ProviderProfileForm,
    ProviderRegisterForm,
    ReviewForm,
    ServiceForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from .models import (
    Availability,
    Booking,
    Category,
    Complaint,
    Favourite,
    ProviderDocument,
    ProviderProfile,
    ProviderService,
    Review,
    ServiceArea,
    User,
    notify,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(value, cast):
    try:
        return cast(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _visible_reviews():
    return Q(provider__reviews__is_hidden=False)


def _service_queryset():
    """Active services of approved, non-suspended providers, annotated with rating data."""
    return (
        ProviderService.objects.filter(
            is_active=True,
            category__is_active=True,
            provider__verification_status="approved",
            provider__user__is_active=True,
        )
        .select_related("provider__user", "category")
        .annotate(
            rating=Avg("provider__reviews__rating", filter=_visible_reviews()),
            review_count=Count("provider__reviews", filter=_visible_reviews()),
        )
    )


def _provider_for(user):
    return get_object_or_404(ProviderProfile.objects.select_related("user"), user=user)


def _safe_next(request, fallback):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
def home(request):
    categories = Category.objects.filter(is_active=True)
    featured = (
        ProviderProfile.objects.filter(verification_status="approved", user__is_active=True)
        .select_related("user")
        .prefetch_related("services__category")
        .annotate(
            avg=Avg("reviews__rating", filter=Q(reviews__is_hidden=False)),
            n=Count("reviews", filter=Q(reviews__is_hidden=False)),
        )
        .order_by(F("avg").desc(nulls_last=True), "-experience")[:6]
    )
    testimonials = Review.objects.filter(is_hidden=False, rating__gte=4).select_related(
        "customer", "provider__user"
    )[:3]
    return render(
        request,
        "home.html",
        {"categories": categories, "featured": featured, "testimonials": testimonials},
    )


def services(request):
    return render(
        request, "services.html", {"categories": Category.objects.filter(is_active=True)}
    )


def about(request):
    return render(request, "about.html")


def faq(request):
    return render(request, "faq.html")


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thanks! Your message has been sent to our team.")
        return redirect("contact")
    return render(
        request,
        "form_page.html",
        {
            "title": "Contact us",
            "subtitle": "Questions or feedback? Send us a message.",
            "form": form,
            "submit_label": "Send message",
        },
    )


def providers(request):
    qs = _service_queryset()
    g = request.GET

    category = g.get("category", "").strip()
    if category.isdigit():
        qs = qs.filter(category_id=int(category))

    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(provider__user__first_name__icontains=q)
            | Q(category__name__icontains=q)
            | Q(description__icontains=q)
            | Q(provider__description__icontains=q)
        )

    location = g.get("location", "").strip()
    if location:
        area_ids = ServiceArea.objects.filter(
            Q(city__icontains=location) | Q(locality__icontains=location) | Q(pincode=location)
        ).values("provider_id")
        qs = qs.filter(
            Q(provider__city__icontains=location)
            | Q(provider__locality__icontains=location)
            | Q(provider__pincode=location)
            | Q(provider_id__in=area_ids)
        )

    day = g.get("day", "").strip()
    if day.isdigit() and 0 <= int(day) <= 6:
        qs = qs.filter(
            provider_id__in=Availability.objects.filter(weekday=int(day)).values("provider_id")
        )

    min_price = _num(g.get("min_price"), Decimal)
    max_price = _num(g.get("max_price"), Decimal)
    min_rating = _num(g.get("min_rating"), float)
    if min_price is not None:
        qs = qs.filter(charges__gte=min_price)
    if max_price is not None:
        qs = qs.filter(charges__lte=max_price)
    if min_rating is not None:
        qs = qs.filter(rating__gte=min_rating)

    sort = g.get("sort", "rating")
    ordering = {
        "rating": [F("rating").desc(nulls_last=True), "charges"],
        "price": ["charges"],
        "price_desc": ["-charges"],
        "experience": ["-provider__experience", "charges"],
    }.get(sort, [F("rating").desc(nulls_last=True), "charges"])
    qs = qs.order_by(*ordering, "id")

    page = Paginator(qs, 9).get_page(g.get("page"))
    params = g.copy()
    params.pop("page", None)
    return render(
        request,
        "providers.html",
        {
            "page": page,
            "categories": Category.objects.filter(is_active=True),
            "weekdays": Availability.WEEKDAYS,
            "querystring": params.urlencode(),
            "f": g,
        },
    )


def provider_detail(request, pk):
    profile = get_object_or_404(ProviderProfile.objects.select_related("user"), pk=pk)
    user = request.user
    allowed = profile.is_approved or (
        user.is_authenticated and (user == profile.user or user.role == "admin")
    )
    if not allowed:
        raise Http404
    avg, count = profile.rating_summary()
    is_fav = (
        user.is_authenticated
        and user.role == "customer"
        and Favourite.objects.filter(customer=user, provider=profile).exists()
    )
    return render(
        request,
        "provider_detail.html",
        {
            "p": profile,
            "services": profile.services.filter(is_active=True, category__is_active=True).select_related("category"),
            "availability": profile.availability.all(),
            "areas": profile.areas.all(),
            "reviews": profile.reviews.filter(is_hidden=False).select_related("customer"),
            "avg": avg,
            "count": count,
            "is_fav": is_fav,
        },
    )


def compare(request):
    ids = [int(i) for i in request.GET.getlist("ids") if i.isdigit()][:3]
    items = list(_service_queryset().filter(pk__in=ids)) if ids else []
    if len(items) < 2:
        messages.info(request, "Select at least two providers to compare.")
        return redirect("providers")
    return render(request, "compare.html", {"items": items})


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class SiteLoginView(LoginView):
    form_class = LoginForm
    template_name = "form_page.html"
    redirect_authenticated_user = True
    extra_context = {
        "title": "Log in",
        "submit_label": "Log in",
        "links": [
            ("Forgot password?", reverse_lazy("password_reset")),
            ("Create customer account", reverse_lazy("register")),
            ("Register as a provider", reverse_lazy("register_provider")),
        ],
    }


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = CustomerRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome to HomeServe! Your account is ready.")
        return redirect("dashboard")
    return render(
        request,
        "form_page.html",
        {
            "title": "Create a customer account",
            "form": form,
            "submit_label": "Register",
            "links": [("Already registered? Log in", reverse("login"))],
        },
    )


def register_provider(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = ProviderRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(
            request,
            "Account created. Upload your documents so an administrator can verify you; "
            "you will appear in search once approved.",
        )
        return redirect("provider_manage", kind="documents")
    return render(
        request,
        "form_page.html",
        {
            "title": "Register as a service provider",
            "subtitle": "Your profile goes live after an administrator verifies your documents.",
            "form": form,
            "submit_label": "Register",
            "width": 8,
            "links": [("Already registered? Log in", reverse("login"))],
        },
    )


@login_required
def dashboard(request):
    role = request.user.role
    if role == "provider":
        return redirect("provider_dashboard")
    if role == "admin":
        return redirect("admin_dashboard")
    return redirect("customer_dashboard")


class SitePasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "form_page.html"
    success_url = reverse_lazy("profile")
    extra_context = {"title": "Change password", "submit_label": "Update password"}

    def form_valid(self, form):
        messages.success(self.request, "Your password was changed.")
        return super().form_valid(form)


class SitePasswordResetView(PasswordResetView):
    form_class = StyledPasswordResetForm
    template_name = "form_page.html"
    success_url = reverse_lazy("password_reset_done")
    extra_context = {
        "title": "Reset your password",
        "subtitle": "Enter your email and we will send you a reset link.",
        "submit_label": "Send reset link",
    }


class SitePasswordResetDoneView(PasswordResetDoneView):
    template_name = "message_page.html"
    extra_context = {
        "title": "Check your email",
        "message": "If an account exists for that address, a reset link has been sent. "
        "(In development the email is printed in the terminal running the server.)",
    }


class SitePasswordResetConfirmView(PasswordResetConfirmView):
    form_class = StyledSetPasswordForm
    template_name = "form_page.html"
    success_url = reverse_lazy("password_reset_complete")
    extra_context = {"title": "Choose a new password", "submit_label": "Save password"}


class SitePasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "message_page.html"
    extra_context = {
        "title": "Password updated",
        "message": "Your password has been changed. You can now log in.",
        "link_url": reverse_lazy("login"),
        "link_label": "Go to login",
    }


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
@role_required("customer")
def customer_dashboard(request):
    all_bookings = Booking.objects.filter(customer=request.user)
    status = request.GET.get("status", "")
    bookings = all_bookings.select_related("provider_service__provider__user", "provider_service__category")
    if status in dict(Booking.STATUS_CHOICES):
        bookings = bookings.filter(status=status)
    stats = {
        "total": all_bookings.count(),
        "pending": all_bookings.filter(status="pending").count(),
        "active": all_bookings.filter(status__in=("accepted", "in_progress")).count(),
        "completed": all_bookings.filter(status="completed").count(),
    }
    return render(
        request,
        "customer_dashboard.html",
        {
            "bookings": bookings,
            "stats": stats,
            "status": status,
            "statuses": Booking.STATUS_CHOICES,
        },
    )


@role_required("customer")
def book(request, service_id):
    service = get_object_or_404(_service_queryset(), pk=service_id)
    form = BookingForm(
        request.POST or None,
        service=service,
        initial={"address": request.user.address},
    )
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        booking = Booking.objects.create(
            customer=request.user,
            provider_service=service,
            booking_date=cd["booking_date"],
            booking_time=cd["booking_time"],
            address=cd["address"],
            notes=cd["notes"],
            is_emergency=cd["is_emergency"],
            amount=service.charges,
            status="pending",
        )
        notify(
            service.provider.user,
            f"New booking request #{booking.pk} for {service.category.name} on "
            f"{booking.booking_date} at {booking.booking_time:%H:%M}.",
            reverse("booking_detail", args=[booking.pk]),
        )
        messages.success(request, "Booking submitted. You will be notified when the provider responds.")
        return redirect("booking_detail", pk=booking.pk)
    return render(
        request,
        "form_page.html",
        {
            "title": f"Book {service.category.name}",
            "subtitle": f"{service.provider} · ₹{service.charges} per visit",
            "form": form,
            "submit_label": "Request booking",
            "back_url": reverse("provider_detail", args=[service.provider_id]),
        },
    )


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "provider_service__provider__user", "provider_service__category"),
        pk=pk,
    )
    user = request.user
    is_customer = booking.customer_id == user.id
    is_provider = booking.provider_service.provider.user_id == user.id
    if not (is_customer or is_provider or user.role == "admin"):
        raise PermissionDenied
    return render(
        request,
        "booking_detail.html",
        {
            "b": booking,
            "is_customer": is_customer,
            "is_provider": is_provider,
            "review": Review.objects.filter(booking=booking).first(),
        },
    )


@login_required
@require_POST
def booking_action(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "provider_service__provider__user", "provider_service__category"),
        pk=pk,
    )
    user = request.user
    targets = {
        "accept": "accepted",
        "reject": "rejected",
        "start": "in_progress",
        "complete": "completed",
        "cancel": "cancelled",
    }
    action = request.POST.get("action")
    fallback = reverse("booking_detail", args=[booking.pk])
    if action not in targets:
        messages.error(request, "Unknown action.")
        return redirect(fallback)

    is_customer = booking.customer_id == user.id
    is_provider = booking.provider_service.provider.user_id == user.id
    if action == "cancel" and not is_customer:
        raise PermissionDenied
    if action != "cancel" and not is_provider:
        raise PermissionDenied

    new_status = targets[action]
    if new_status not in Booking.TRANSITIONS.get(booking.status, []):
        messages.error(
            request,
            f"This booking is {booking.get_status_display().lower()} and cannot be changed that way.",
        )
        return redirect(_safe_next(request, fallback))
    if action == "cancel" and not booking.can_cancel():
        messages.error(request, "Too close to the start time to cancel online. Please contact the provider.")
        return redirect(_safe_next(request, fallback))
    if action == "accept" and booking.has_conflict():
        messages.error(request, "You already have a confirmed job that overlaps this time slot.")
        return redirect(_safe_next(request, fallback))

    booking.status = new_status
    if action == "reject":
        booking.rejection_reason = request.POST.get("reason", "").strip()[:255]
    booking.save()

    label = booking.get_status_display().lower()
    link = reverse("booking_detail", args=[booking.pk])
    if is_customer:
        notify(booking.provider_service.provider.user, f"Booking #{booking.pk} was cancelled by the customer.", link)
    else:
        notify(booking.customer, f"Your booking #{booking.pk} is now {label}.", link)
    messages.success(request, f"Booking #{booking.pk} marked as {label}.")
    return redirect(_safe_next(request, fallback))


@role_required("customer")
def review_create(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("provider_service__provider__user"),
        pk=booking_id,
        customer=request.user,
    )
    if booking.status != "completed":
        messages.error(request, "You can review a service only after it is completed.")
        return redirect("booking_detail", pk=booking.pk)
    if Review.objects.filter(booking=booking).exists():
        messages.error(request, "You have already reviewed this booking.")
        return redirect("booking_detail", pk=booking.pk)

    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        review = form.save(commit=False)
        review.booking = booking
        review.customer = request.user
        review.provider = booking.provider_service.provider
        try:
            review.save()
        except IntegrityError:
            messages.error(request, "You have already reviewed this booking.")
            return redirect("booking_detail", pk=booking.pk)
        notify(
            booking.provider_service.provider.user,
            f"You received a {review.rating}-star review for booking #{booking.pk}.",
            reverse("booking_detail", args=[booking.pk]),
        )
        messages.success(request, "Thank you for your review!")
        return redirect("booking_detail", pk=booking.pk)
    return render(
        request,
        "form_page.html",
        {
            "title": f"Review {booking.provider_service.provider}",
            "subtitle": f"Booking #{booking.pk} · {booking.provider_service.category.name}",
            "form": form,
            "submit_label": "Submit review",
            "back_url": reverse("booking_detail", args=[booking.pk]),
        },
    )


@role_required("customer")
def favourites(request):
    items = (
        Favourite.objects.filter(customer=request.user)
        .select_related("provider__user")
        .prefetch_related("provider__services__category")
    )
    return render(request, "favourites.html", {"items": items})


@role_required("customer")
@require_POST
def favourite_toggle(request, provider_id):
    provider = get_object_or_404(ProviderProfile, pk=provider_id, verification_status="approved")
    fav, created = Favourite.objects.get_or_create(customer=request.user, provider=provider)
    if created:
        messages.success(request, f"{provider} added to your favourites.")
    else:
        fav.delete()
        messages.info(request, f"{provider} removed from your favourites.")
    return redirect(_safe_next(request, reverse("provider_detail", args=[provider.pk])))


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(
        request,
        "form_page.html",
        {
            "title": "My profile",
            "subtitle": f"Signed in as {request.user.email}",
            "form": form,
            "submit_label": "Save changes",
            "links": [("Change password", reverse("password_change"))],
        },
    )


@role_required("customer")
def complaints(request):
    items = Complaint.objects.filter(customer=request.user).select_related("provider__user", "booking")
    return render(request, "complaints.html", {"items": items})


@role_required("customer")
def complaint_create(request):
    initial = {}
    booking_id = request.GET.get("booking", "")
    if booking_id.isdigit():
        initial["booking"] = int(booking_id)
    form = ComplaintForm(request.POST or None, customer=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        complaint = form.save(commit=False)
        complaint.customer = request.user
        if complaint.booking:
            complaint.provider = complaint.booking.provider_service.provider
        complaint.save()
        messages.success(request, "Your complaint was submitted. We will review it shortly.")
        return redirect("complaints")
    return render(
        request,
        "form_page.html",
        {
            "title": "Raise a complaint",
            "form": form,
            "submit_label": "Submit complaint",
            "back_url": reverse("complaints"),
        },
    )


@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:100])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "notifications.html", {"items": items})


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
@role_required("provider")
def provider_dashboard(request):
    profile_ = _provider_for(request.user)
    bookings = Booking.objects.filter(provider_service__provider=profile_).select_related(
        "customer", "provider_service__category"
    )
    pending = bookings.filter(status="pending").order_by("booking_date", "booking_time")
    upcoming = bookings.filter(status__in=("accepted", "in_progress")).order_by("booking_date", "booking_time")
    avg, count = profile_.rating_summary()
    earnings = bookings.filter(status="completed").aggregate(t=Sum("amount"))["t"] or 0
    return render(
        request,
        "provider_dashboard.html",
        {
            "p": profile_,
            "pending": pending,
            "upcoming": upcoming,
            "stats": {
                "pending": pending.count(),
                "upcoming": upcoming.count(),
                "completed": bookings.filter(status="completed").count(),
                "earnings": earnings,
                "avg": avg,
                "reviews": count,
            },
            "checklist": {
                "documents": profile_.documents.exists(),
                "services": profile_.services.filter(is_active=True).exists(),
                "availability": profile_.availability.exists(),
            },
        },
    )


@role_required("provider")
def provider_bookings(request):
    profile_ = _provider_for(request.user)
    status = request.GET.get("status", "")
    bookings = Booking.objects.filter(provider_service__provider=profile_).select_related(
        "customer", "provider_service__category"
    )
    if status in dict(Booking.STATUS_CHOICES):
        bookings = bookings.filter(status=status)
    total = bookings.filter(status="completed").aggregate(t=Sum("amount"))["t"] or 0
    return render(
        request,
        "provider_bookings.html",
        {"bookings": bookings, "status": status, "statuses": Booking.STATUS_CHOICES, "total": total},
    )


@role_required("provider")
def provider_profile(request):
    profile_ = _provider_for(request.user)
    form = ProviderContactForm(request.POST or None, instance=request.user)
    form2 = ProviderProfileForm(request.POST or None, request.FILES or None, instance=profile_)
    if request.method == "POST" and all([form.is_valid(), form2.is_valid()]):
        try:
            form.save()
            form2.save()
        except OSError:
            messages.error(request, "Could not store the photo (file storage unavailable). Please try again.")
            return redirect("provider_profile")
        messages.success(request, "Profile updated.")
        return redirect("provider_profile")
    return render(
        request,
        "form_page.html",
        {
            "title": "Provider profile",
            "form": form,
            "form2": form2,
            "submit_label": "Save profile",
            "width": 8,
            "links": [
                ("View public profile", reverse("provider_detail", args=[profile_.pk])),
                ("Change password", reverse("password_change")),
            ],
        },
    )


MANAGE_KINDS = {
    "services": "Services & charges",
    "areas": "Service areas",
    "availability": "Working hours",
    "documents": "Verification documents",
}


@role_required("provider")
def provider_manage(request, kind):
    if kind not in MANAGE_KINDS:
        raise Http404
    profile_ = _provider_for(request.user)
    form_class = {
        "services": ServiceForm,
        "areas": AreaForm,
        "availability": AvailabilityForm,
        "documents": DocumentForm,
    }[kind]
    form = form_class(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        if kind == "services":
            cd = form.cleaned_data
            ProviderService.objects.update_or_create(
                provider=profile_,
                category=cd["category"],
                defaults={
                    "charges": cd["charges"],
                    "description": cd["description"],
                    "is_active": True,
                },
            )
        else:
            obj = form.save(commit=False)
            obj.provider = profile_
            try:
                obj.save()
            except OSError:
                messages.error(request, "Could not store the file (file storage unavailable). Please try again.")
                return redirect("provider_manage", kind=kind)
            if kind == "documents" and profile_.verification_status == "rejected":
                profile_.verification_status = "pending"
                profile_.save(update_fields=["verification_status"])
        messages.success(request, "Saved.")
        return redirect("provider_manage", kind=kind)

    rows = []
    if kind == "services":
        for s in profile_.services.filter(is_active=True).select_related("category"):
            rows.append({"pk": s.pk, "text": f"{s.category.name} — ₹{s.charges}", "sub": s.description})
    elif kind == "areas":
        for a in profile_.areas.all():
            rows.append({"pk": a.pk, "text": f"{a.locality}, {a.city} — {a.pincode}", "sub": ""})
    elif kind == "availability":
        for a in profile_.availability.all():
            rows.append(
                {"pk": a.pk, "text": f"{a.get_weekday_display()}: {a.start_time:%H:%M} – {a.end_time:%H:%M}", "sub": ""}
            )
    else:
        for d in profile_.documents.all():
            rows.append(
                {
                    "pk": d.pk,
                    "text": d.get_document_type_display(),
                    "sub": f"Status: {d.get_status_display()}",
                    "url": reverse("document_download", args=[d.pk]),
                }
            )
    return render(
        request,
        "provider_manage.html",
        {
            "kind": kind,
            "title": MANAGE_KINDS[kind],
            "tabs": MANAGE_KINDS.items(),
            "form": form,
            "rows": rows,
            "p": profile_,
        },
    )


@role_required("provider")
@require_POST
def provider_delete(request, kind, pk):
    if kind not in MANAGE_KINDS:
        raise Http404
    profile_ = _provider_for(request.user)
    if kind == "services":
        service = get_object_or_404(ProviderService, pk=pk, provider=profile_)
        if profile_.services.filter(is_active=True).count() <= 1:
            messages.error(request, "You must offer at least one service.")
        else:
            service.is_active = False  # kept (not deleted) so past bookings stay intact
            service.save(update_fields=["is_active"])
            messages.success(request, "Service removed.")
    else:
        model = {"areas": ServiceArea, "availability": Availability, "documents": ProviderDocument}[kind]
        obj = get_object_or_404(model, pk=pk, provider=profile_)
        if kind == "documents":
            try:
                obj.file.delete(save=False)
            except OSError:
                messages.error(request, "Could not delete the file (file storage unavailable). Please try again.")
                return redirect("provider_manage", kind=kind)
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("provider_manage", kind=kind)


@login_required
def document_download(request, pk):
    doc = get_object_or_404(ProviderDocument.objects.select_related("provider"), pk=pk)
    if request.user.role != "admin" and doc.provider.user_id != request.user.id:
        raise PermissionDenied
    ctype = mimetypes.guess_type(doc.file.name)[0] or "application/octet-stream"
    try:
        return FileResponse(doc.file.open("rb"), content_type=ctype)
    except FileNotFoundError:
        raise Http404("File missing")
    except OSError:
        return HttpResponse("The file storage is temporarily unavailable. Try again shortly.", status=503)


# ---------------------------------------------------------------------------
# Administrator (custom panel; bulk data management uses /django-admin/)
# ---------------------------------------------------------------------------
@role_required("admin")
def admin_dashboard(request):
    bookings = Booking.objects.all()
    stats = {
        "customers": User.objects.filter(role="customer").count(),
        "providers": ProviderProfile.objects.count(),
        "approved": ProviderProfile.objects.filter(verification_status="approved").count(),
        "pending_verification": ProviderProfile.objects.filter(verification_status="pending").count(),
        "categories": Category.objects.count(),
        "bookings": bookings.count(),
        "pending_bookings": bookings.filter(status="pending").count(),
        "completed_bookings": bookings.filter(status="completed").count(),
        "cancelled_bookings": bookings.filter(status="cancelled").count(),
        "complaints": Complaint.objects.count(),
        "open_complaints": Complaint.objects.exclude(status="resolved").count(),
    }

    # Bookings per month for the last 6 months (computed in Python: DB-agnostic).
    today = timezone.localdate()
    months = []
    y, m = today.year, today.month
    for _ in range(6):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    since = timezone.now() - timedelta(days=200)
    counter = Counter()
    for created in bookings.filter(created_at__gte=since).values_list("created_at", flat=True):
        local = timezone.localtime(created)
        counter[(local.year, local.month)] += 1
    month_labels = [f"{y}-{m:02d}" for y, m in months]
    month_values = [counter.get(key, 0) for key in months]

    popular = Category.objects.annotate(n=Count("provider_services__bookings")).order_by("-n", "name")[:6]
    top_providers = (
        ProviderProfile.objects.filter(verification_status="approved")
        .select_related("user")
        .annotate(
            avg=Avg("reviews__rating", filter=Q(reviews__is_hidden=False)),
            n=Count("reviews", filter=Q(reviews__is_hidden=False)),
        )
        .filter(n__gt=0)
        .order_by("-avg", "-n")[:5]
    )
    return render(
        request,
        "admin_dashboard.html",
        {
            "stats": stats,
            "top_providers": top_providers,
            "chart_data": {
                "months": month_labels,
                "monthly": month_values,
                "categories": [c.name for c in popular],
                "category_counts": [c.n for c in popular],
            },
        },
    )


@role_required("admin")
def admin_providers(request):
    status = request.GET.get("status", "pending")
    qs = ProviderProfile.objects.select_related("user").annotate(doc_count=Count("documents"))
    if status in dict(ProviderProfile.STATUS_CHOICES):
        qs = qs.filter(verification_status=status)
    else:
        status = "all"
    return render(
        request,
        "admin_providers.html",
        {"items": qs, "status": status, "statuses": ProviderProfile.STATUS_CHOICES},
    )


@role_required("admin")
def admin_provider_detail(request, pk):
    p = get_object_or_404(ProviderProfile.objects.select_related("user"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        remarks = request.POST.get("remarks", "").strip()
        if action == "approve":
            if not p.documents.exists():
                messages.error(request, "Cannot approve: the provider has not uploaded any documents.")
            else:
                p.verification_status = "approved"
                p.admin_remarks = remarks
                p.save()
                p.documents.update(status="approved")
                notify(p.user, "Congratulations! Your provider account has been approved.", reverse("provider_dashboard"))
                messages.success(request, "Provider approved.")
        elif action == "reject":
            if not remarks:
                messages.error(request, "Please enter remarks explaining the rejection.")
            else:
                p.verification_status = "rejected"
                p.admin_remarks = remarks
                p.save()
                p.documents.update(status="rejected")
                notify(
                    p.user,
                    f"Your provider application was rejected: {remarks}",
                    reverse("provider_manage", args=["documents"]),
                )
                messages.success(request, "Provider rejected.")
        elif action in ("suspend", "activate"):
            p.user.is_active = action == "activate"
            p.user.save()
            messages.success(request, "Account activated." if p.user.is_active else "Account suspended.")
        return redirect("admin_provider_detail", pk=p.pk)
    return render(
        request,
        "admin_provider_detail.html",
        {"p": p, "documents": p.documents.all(), "services": p.services.select_related("category")},
    )


@role_required("admin")
def admin_report(request, kind):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{kind}_report.csv"'
    writer = csv.writer(response)
    if kind == "bookings":
        writer.writerow(["ID", "Customer", "Provider", "Service", "Date", "Time", "Status", "Amount", "Emergency"])
        for b in Booking.objects.select_related("customer", "provider_service__provider__user", "provider_service__category"):
            writer.writerow([
                b.pk, b.customer.email, b.provider_service.provider.user.email,
                b.provider_service.category.name, b.booking_date, b.booking_time.strftime("%H:%M"),
                b.status, b.amount, "yes" if b.is_emergency else "no",
            ])
    elif kind == "customers":
        writer.writerow(["ID", "Name", "Email", "Phone", "City", "Pincode", "Active", "Joined"])
        for u in User.objects.filter(role="customer"):
            writer.writerow([u.pk, u.get_full_name(), u.email, u.phone, u.city, u.pincode, u.is_active, u.date_joined.date()])
    elif kind == "providers":
        writer.writerow(["ID", "Name", "Email", "Phone", "City", "Locality", "Pincode", "Experience", "Status"])
        for p in ProviderProfile.objects.select_related("user"):
            writer.writerow([p.pk, p.user.get_full_name(), p.user.email, p.user.phone, p.city, p.locality, p.pincode, p.experience, p.verification_status])
    else:
        raise Http404
    return response
