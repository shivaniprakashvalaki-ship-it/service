from pathlib import Path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse
from django.urls import include, path
from django.views.decorators.cache import cache_control

_CSS = Path(__file__).resolve().parent / "style.css"


@cache_control(max_age=3600, public=True)
def style_css(request):
    """The site stylesheet. Served explicitly because the project has no static/ folder."""
    return FileResponse(open(_CSS, "rb"), content_type="text/css; charset=utf-8")


urlpatterns = [
    path("style.css", style_css, name="style_css"),
    path("django-admin/", admin.site.urls),
    path("", include("core.site_urls")),
]

# Only used with USE_SUPABASE=0 (local-disk fallback)
if settings.DEBUG and not settings.SUPABASE_ENABLED:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
