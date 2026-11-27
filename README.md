# HomeServe – Home Service Finder & Booking System (Django + Supabase Storage)

Customers search, compare, book and review home-service professionals; providers register,
upload verification documents and handle bookings; admins verify providers.

**Every file is in ONE folder (no sub-folders).** Extract the zip, and you are in the project root.

## Where the files go (Supabase Storage)

| What | Bucket | Visibility |
|---|---|---|
| Provider photos | `photos` | public (direct image URLs) |
| Verification documents (ID proofs…) | `documents` | **private** – streamed by Django only to the owner and admins |

Project URL and publishable key are already the defaults in `settings.py`
(`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`) and can be overridden with environment variables.

### One-time Supabase setup (required – the app cannot create buckets itself)
1. Supabase Dashboard → **SQL Editor** → paste and run `supabase_setup.sql`.
2. **Recommended for production:** Dashboard → Project Settings → API Keys → copy the **secret** key and
   set it as the server env var `SUPABASE_SECRET_KEY`, then skip the "Policies" part of the SQL.
   With only the publishable key, the SQL must open the `documents` bucket to anyone who has that key,
   i.e. ID proofs become readable by anyone who finds the key. The secret key must never be in
   templates, JavaScript or a public repo.
3. Check it works: `python check_supabase.py` (uploads, reads and deletes a test file in both buckets).

## Run locally
```bash
python -m venv venv
venv\Scripts\activate            # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python seed.py                   # creates migrations/ + database + DEMO data
python manage.py runserver       # http://127.0.0.1:8000/
```
No internet / no Supabase yet? Run with `USE_SUPABASE=0` and files go to local `media/` folders instead.

Demo accounts (`seed.py` only – do NOT run seed.py in production, the passwords are public):
admin@homeserve.com / Admin@12345 · customer@demo.com / Demo@12345 · suresh@demo.com / Demo@12345 · pending@demo.com / Demo@12345.
Log in with the **email**. Admin panel `/panel/`, data admin `/django-admin/`.

## Deploy (Render / Railway / any Python host)
Build command: `pip install -r requirements.txt`
Start command (same as the included `Procfile`):
```
python manage.py makemigrations core --noinput && python manage.py migrate --noinput && gunicorn wsgi:application --bind 0.0.0.0:$PORT
```
Environment variables: see `env.example`. Minimum: `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `SUPABASE_SECRET_KEY`, `DATABASE_URL`.
Create your admin once: `python manage.py createsuperuser` (use your email as username).

### Things you must know
- **Database:** without `DATABASE_URL` the app uses SQLite, which most hosts wipe on every deploy.
  Use a PostgreSQL URL: Supabase → Connect → **Session pooler** (port 5432) or Direct connection. Do not use the port-6543 transaction pooler. For a non-SSL local Postgres set `DATABASE_SSLMODE=disable`.
- **Migrations:** `migrations/` is generated on first run (it is not in the zip). On a host with an ephemeral
  disk, commit the generated `migrations/` folder to your repo after the first run, otherwise a later
  model change cannot be migrated safely against an existing database.
- **Emails** are printed to the log (console backend); configure SMTP if you need real mail.
- **Flat layout trick:** `settings.py` registers this folder as the Django app package `core`, so
  `core.models` is `models.py`, `core.views` is `views.py`, and so on. Do not rename those files.

## Files
`manage.py wsgi.py settings.py urls.py site_urls.py` – project wiring · `models.py forms.py views.py admin.py apps.py decorators.py context_processors.py` – app ·
`supabase_client.py supabase_storage.py` – Supabase Storage · `*.html style.css` – UI · `seed.py` – demo data ·
`check_supabase.py supabase_setup.sql env.example Procfile requirements.txt`.

## Business rules (unchanged)
Unique email; hashed passwords; role-based access (403 on wrong role); only admin-approved providers are searchable;
admin cannot approve without documents, rejection needs remarks; booking flow Pending → Accepted → In Progress → Completed
(Pending → Rejected; Pending/Accepted → Cancelled, accepted only ≥ 2 h before start); past dates and out-of-hours slots blocked;
overlapping confirmed jobs blocked; one 1–5★ review per completed booking; customer phone/address revealed after acceptance;
CSRF on all forms; uploads limited to 2 MB (photos) / 5 MB PDF-JPG-PNG (documents).
