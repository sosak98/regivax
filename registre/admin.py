"""Enregistrement des modèles du registre dans l'interface d'administration."""

from django.contrib import admin

from .models import Agent, Centre, Dose, Enfant


@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ("nom", "commune", "zone_sanitaire", "code_fosa", "telephone")
    search_fields = ("nom", "commune", "zone_sanitaire", "code_fosa")


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "centre", "fonction")
    list_filter = ("centre",)
    search_fields = ("utilisateur__username", "utilisateur__last_name", "fonction")


class DoseInline(admin.TabularInline):
    model = Dose
    extra = 0


@admin.register(Enfant)
class EnfantAdmin(admin.ModelAdmin):
    list_display = ("numero", "nom", "prenom", "sexe", "date_naissance", "nom_mere", "centre")
    list_filter = ("centre", "sexe")
    search_fields = ("numero", "nom", "prenom", "nom_mere")
    inlines = [DoseInline]


@admin.register(Dose)
class DoseAdmin(admin.ModelAdmin):
    list_display = ("enfant", "cle", "date_administration", "lot", "agent", "date_saisie")
    list_filter = ("date_administration", "cle", "enfant__centre")
    search_fields = ("enfant__numero", "enfant__nom", "enfant__prenom", "lot")
