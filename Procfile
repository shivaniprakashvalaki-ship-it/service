web: python manage.py makemigrations core --noinput && python manage.py migrate --noinput && gunicorn wsgi:application --bind 0.0.0.0:${PORT:-8000}
