from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# Titles shown at the top of the Django Admin Panel
admin.site.site_header = "TrafficVerify BD - Admin (DEMO SYSTEM)"
admin.site.site_title = "TrafficVerify BD Admin"
admin.site.index_title = "Demo data management (all records are fictional)"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", include("dashboard.admin_urls")),
    path("dashboard/", include("dashboard.urls")),
    path("vehicles/", include("vehicles.urls")),
    path("licences/", include("licences.urls")),
    path("", include("accounts.urls")),
]

# During development only: lets the browser show uploaded demo photos.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)