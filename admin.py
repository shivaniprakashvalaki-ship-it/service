from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import (
    Availability,
    Booking,
    Category,
    Complaint,
    ContactMessage,
    Favourite,
    Notification,
    ProviderDocument,
    ProviderProfile,
    ProviderService,
    Review,
    ServiceArea,
    User,
)

admin.site.site_header = "HomeServe administration"
admin.site.site_title = "HomeServe admin"
admin.site.index_title = "Manage customers, providers, bookings and content"


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role")


class AdminUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    list_display = ("email", "first_name", "role", "phone", "city", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "phone", "pincode")
    ordering = ("email",)
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("HomeServe", {"fields": ("role", "phone", "address", "city", "pincode")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "email", "role", "password1", "password2")}),
    )
    actions = ["suspend_accounts", "reactivate_accounts"]

    @admin.action(description="Suspend selected accounts")
    def suspend_accounts(self, request, queryset):
        queryset.exclude(pk=request.user.pk).update(is_active=False)

    @admin.action(description="Reactivate selected accounts")
    def reactivate_accounts(self, request, queryset):
        queryset.update(is_active=True)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)


class ProviderServiceInline(admin.TabularInline):
    model = ProviderService
    extra = 0


class ProviderDocumentInline(admin.TabularInline):
    model = ProviderDocument
    extra = 0


@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "locality", "pincode", "experience", "verification_status")
    list_filter = ("verification_status", "city")
    search_fields = ("user__first_name", "user__email", "pincode")
    inlines = [ProviderServiceInline, ProviderDocumentInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "provider_service", "booking_date", "booking_time", "status", "amount", "is_emergency")
    list_filter = ("status", "is_emergency", "booking_date")
    search_fields = ("customer__email", "provider_service__provider__user__first_name")
    date_hierarchy = "booking_date"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("provider", "customer", "rating", "is_hidden", "created_at")
    list_filter = ("rating", "is_hidden")
    list_editable = ("is_hidden",)
    search_fields = ("comment", "provider__user__first_name")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("subject", "customer", "provider", "status", "created_at")
    list_filter = ("status",)
    list_editable = ("status",)
    search_fields = ("subject", "description", "customer__email")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "created_at")
    search_fields = ("subject", "name", "email")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "is_read", "created_at")
    list_filter = ("is_read",)


admin.site.register([ProviderService, ServiceArea, Availability, ProviderDocument, Favourite])
