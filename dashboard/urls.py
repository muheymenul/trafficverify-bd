from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("history/", views.history, name="history"),
    path("settings/", views.account_settings, name="settings"),
    path("settings/password/", views.OfficerPasswordChangeView.as_view(), name="password_change"),
]