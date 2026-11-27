from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    # Public
    path("", views.home, name="home"),
    path("services/", views.services, name="services"),
    path("providers/", views.providers, name="providers"),
    path("providers/<int:pk>/", views.provider_detail, name="provider_detail"),
    path("compare/", views.compare, name="compare"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    # Auth
    path("login/", views.SiteLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("register/provider/", views.register_provider, name="register_provider"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("password/change/", views.SitePasswordChangeView.as_view(), name="password_change"),
    path("password/reset/", views.SitePasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", views.SitePasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password/reset/<uidb64>/<token>/",
        views.SitePasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("password/reset/complete/", views.SitePasswordResetCompleteView.as_view(), name="password_reset_complete"),
    # Customer
    path("customer/", views.customer_dashboard, name="customer_dashboard"),
    path("book/<int:service_id>/", views.book, name="book"),
    path("bookings/<int:pk>/", views.booking_detail, name="booking_detail"),
    path("bookings/<int:pk>/action/", views.booking_action, name="booking_action"),
    path("review/<int:booking_id>/", views.review_create, name="review_create"),
    path("favourites/", views.favourites, name="favourites"),
    path("favourites/<int:provider_id>/toggle/", views.favourite_toggle, name="favourite_toggle"),
    path("profile/", views.profile, name="profile"),
    path("complaints/", views.complaints, name="complaints"),
    path("complaints/new/", views.complaint_create, name="complaint_create"),
    path("notifications/", views.notifications, name="notifications"),
    # Provider
    path("provider/", views.provider_dashboard, name="provider_dashboard"),
    path("provider/bookings/", views.provider_bookings, name="provider_bookings"),
    path("provider/profile/", views.provider_profile, name="provider_profile"),
    path("provider/manage/<str:kind>/", views.provider_manage, name="provider_manage"),
    path("provider/delete/<str:kind>/<int:pk>/", views.provider_delete, name="provider_delete"),
    path("documents/<int:pk>/", views.document_download, name="document_download"),
    # Administrator
    path("panel/", views.admin_dashboard, name="admin_dashboard"),
    path("panel/providers/", views.admin_providers, name="admin_providers"),
    path("panel/providers/<int:pk>/", views.admin_provider_detail, name="admin_provider_detail"),
    path("panel/report/<str:kind>/", views.admin_report, name="admin_report"),
]
