"""Routes de l'application registre."""

from django.urls import path

from . import views

app_name = "registre"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("enfant/nouveau/", views.nouvel_enfant, name="nouvel_enfant"),
    path("enfant/<int:pk>/", views.enfant, name="enfant"),
    path("enfant/<int:pk>/rendez-vous/", views.rendez_vous, name="rendez_vous"),
    path("seance/", views.seance, name="seance"),
    path("seance/dhis2.json", views.seance_dhis2_json, name="seance_dhis2_json"),
    path("seance/dhis2.csv", views.seance_dhis2_csv, name="seance_dhis2_csv"),
    path("connexion/", views.connexion, name="connexion"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
]
