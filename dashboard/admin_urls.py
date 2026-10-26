from django.urls import path

from . import admin_views

app_name = "adminpanel"

urlpatterns = [
    path("", admin_views.home, name="home"),
    path("officers/", admin_views.officers, name="officers"),
    path("vehicles/", admin_views.vehicles, name="vehicles"),
    path("licences/", admin_views.licences, name="licences"),
    path("logs/", admin_views.logs, name="logs"),
]