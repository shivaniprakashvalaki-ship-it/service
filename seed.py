"""One-command setup: creates migrations, builds the database, loads demo data.

    python seed.py

Safe to run again: it will not duplicate demo data.
"""
import os
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402

ADMIN_PASSWORD = "Admin@12345"
DEMO_PASSWORD = "Demo@12345"


def main():
    call_command("makemigrations", "core", interactive=False)
    call_command("migrate", interactive=False)

    from datetime import time

    from core.models import (
        Availability,
        Booking,
        Category,
        ProviderProfile,
        ProviderService,
        Review,
        User,
    )

    if User.objects.filter(email="admin@homeserve.com").exists():
        print("Demo data already present - nothing to do.")
        return

    User.objects.create_superuser(
        username="admin@homeserve.com",
        email="admin@homeserve.com",
        password=ADMIN_PASSWORD,
        first_name="Site Admin",
    )

    categories = {}
    for name, icon, desc in [
        ("Plumbing", "bi-droplet", "Leaks, taps, pipes, fittings"),
        ("Electrical", "bi-lightning-charge", "Wiring, switches, fans, lights"),
        ("Carpentry", "bi-hammer", "Furniture, doors, repairs"),
        ("Painting", "bi-palette", "Interior and exterior painting"),
        ("Home Cleaning", "bi-stars", "Deep cleaning and sanitising"),
        ("AC Repair", "bi-snow", "Service, gas refill, installation"),
        ("Pest Control", "bi-bug", "Termites, cockroaches, rodents"),
        ("Appliance Repair", "bi-tools", "Washing machine, fridge, microwave"),
    ]:
        categories[name] = Category.objects.create(name=name, icon=icon, description=desc)

    providers = [
        ("Suresh Kumar", "suresh@demo.com", "9876500001", "Indiranagar", "560038", 12, {"Plumbing": 450, "Appliance Repair": 600}, "Licensed plumber, 12 years in residential work."),
        ("Mohan Rao", "mohan@demo.com", "9876500002", "Koramangala", "560034", 9, {"Electrical": 400, "AC Repair": 700}, "Certified electrician; AC servicing specialist."),
        ("Ravi Shankar", "ravi.s@demo.com", "9876500003", "Whitefield", "560066", 15, {"Carpentry": 550}, "Custom furniture and door repairs."),
        ("Lakshmi Devi", "lakshmi@demo.com", "9876500004", "Jayanagar", "560011", 6, {"Home Cleaning": 800, "Pest Control": 900}, "Deep-cleaning crew leader."),
        ("Imran Khan", "imran@demo.com", "9876500005", "HSR Layout", "560102", 8, {"Painting": 650, "Carpentry": 500}, "Interior painting and finishing."),
    ]
    created = []
    for name, email, phone, locality, pin, exp, svc, desc in providers:
        user = User.objects.create_user(
            username=email, email=email, password=DEMO_PASSWORD, first_name=name,
            role="provider", phone=phone, city="Bengaluru", pincode=pin,
        )
        profile = ProviderProfile.objects.create(
            user=user, experience=exp, description=desc, city="Bengaluru",
            locality=locality, pincode=pin, verification_status="approved",
        )
        for cat, price in svc.items():
            ProviderService.objects.create(provider=profile, category=categories[cat], charges=price)
        for day in range(6):  # Monday-Saturday
            Availability.objects.create(provider=profile, weekday=day, start_time=time(9, 0), end_time=time(18, 0))
        created.append(profile)

    # One provider still waiting for verification (log in, upload a document, then approve as admin).
    pending_user = User.objects.create_user(
        username="pending@demo.com", email="pending@demo.com", password=DEMO_PASSWORD,
        first_name="Arjun Nair", role="provider", phone="9876500009", city="Bengaluru", pincode="560003",
    )
    pending = ProviderProfile.objects.create(
        user=pending_user, experience=4, description="New plumber awaiting verification.",
        city="Bengaluru", locality="Malleshwaram", pincode="560003",
    )
    ProviderService.objects.create(provider=pending, category=categories["Plumbing"], charges=400)

    customers = []
    for name, email in [("Anita Sharma", "customer@demo.com"), ("Ravi Menon", "ravi@demo.com"), ("Meera Iyer", "meera@demo.com")]:
        customers.append(
            User.objects.create_user(
                username=email, email=email, password=DEMO_PASSWORD, first_name=name,
                role="customer", phone="9812345678", city="Bengaluru", pincode="560001",
                address="12, MG Road, Bengaluru",
            )
        )

    # Completed jobs + reviews so ratings, charts and the compare page have data.
    ratings = [(5, "Quick and professional."), (4, "Good work, arrived on time."), (5, "Very neat. Would hire again."), (3, "Fine, but a bit late.")]
    today = timezone.localdate()
    n = 0
    for i, profile in enumerate(created):
        service = profile.services.first()
        for j in range(2):
            customer = customers[(i + j) % len(customers)]
            booking = Booking.objects.create(
                customer=customer, provider_service=service,
                booking_date=today - timedelta(days=10 + i * 3 + j),
                booking_time=time(10 + j, 0), address=customer.address,
                status="completed", amount=service.charges,
            )
            Booking.objects.filter(pk=booking.pk).update(
                created_at=timezone.now() - timedelta(days=40 * j + 12 + i * 3)
            )
            rating, comment = ratings[n % len(ratings)]
            Review.objects.create(booking=booking, customer=customer, provider=profile, rating=rating, comment=comment)
            n += 1

    print("\nDemo data loaded.\n")
    print("  Admin     : admin@homeserve.com   /", ADMIN_PASSWORD)
    print("  Customer  : customer@demo.com     /", DEMO_PASSWORD)
    print("  Provider  : suresh@demo.com       /", DEMO_PASSWORD, "(approved)")
    print("  Provider  : pending@demo.com      /", DEMO_PASSWORD, "(awaiting verification)")
    print("\nNow run:  python manage.py runserver   and open http://127.0.0.1:8000/\n")


if __name__ == "__main__":
    main()
