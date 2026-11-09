"""Formulaires de saisie et d'authentification pour RegiVax."""

from datetime import date

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Enfant


class ConnexionForm(AuthenticationForm):
    """Formulaire de connexion des agents du centre de santé."""

    username = forms.CharField(
        label="Nom d'utilisateur",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "Identifiant de l'agent",
            }
        ),
    )
    password = forms.CharField(
        label="Mot de passe",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Mot de passe",
            }
        ),
    )


class EnfantForm(forms.ModelForm):
    """Formulaire d'inscription d'un enfant au registre du centre."""

    class Meta:
        model = Enfant
        fields = [
            "numero",
            "nom",
            "prenom",
            "sexe",
            "date_naissance",
            "nom_mere",
            "telephone",
            "quartier",
        ]
        widgets = {
            "date_naissance": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "numero": forms.TextInput(attrs={"placeholder": "Ex. : RV-2026-001"}),
            "nom": forms.TextInput(attrs={"placeholder": "Nom de famille"}),
            "prenom": forms.TextInput(attrs={"placeholder": "Prénom"}),
            "nom_mere": forms.TextInput(attrs={"placeholder": "Nom complet de la mère"}),
            "telephone": forms.TextInput(attrs={"placeholder": "Optionnel"}),
            "quartier": forms.TextInput(attrs={"placeholder": "Optionnel"}),
        }

    def __init__(self, *args, centre=None, **kwargs):
        self.centre = centre
        super().__init__(*args, **kwargs)

    def clean_numero(self):
        numero = (self.cleaned_data.get("numero") or "").strip()
        if not numero:
            raise forms.ValidationError("Le numéro du registre papier est obligatoire.")
        if self.centre is not None:
            doublon = Enfant.objects.filter(centre=self.centre, numero=numero)
            if self.instance and self.instance.pk:
                doublon = doublon.exclude(pk=self.instance.pk)
            if doublon.exists():
                raise forms.ValidationError(
                    "Ce numéro de registre est déjà utilisé dans ce centre."
                )
        return numero

    def clean_date_naissance(self):
        date_naissance = self.cleaned_data.get("date_naissance")
        if date_naissance and date_naissance > date.today():
            raise forms.ValidationError(
                "La date de naissance ne peut pas être postérieure à la date du jour."
            )
        return date_naissance
