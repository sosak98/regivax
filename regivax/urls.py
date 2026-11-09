"""Configuration des URL principales du projet RegiVax."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("registre.urls")),
]
