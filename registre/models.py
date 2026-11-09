"""Modèles de données du registre vaccinal RegiVax."""

from django.conf import settings
from django.db import models

from .calendrier import CALENDRIER_PAR_CLE, CALENDRIER_PEV


class Centre(models.Model):
    """Centre de santé disposant de son propre registre vaccinal local."""

    nom = models.CharField("Nom du centre", max_length=150)
    commune = models.CharField("Commune", max_length=120)
    zone_sanitaire = models.CharField("Zone sanitaire", max_length=150)
    code_fosa = models.CharField(
        "Code FOSA",
        max_length=50,
        blank=True,
        default="",
        help_text="Code officiel de la formation sanitaire, s'il est attribué.",
    )
    telephone = models.CharField("Téléphone", max_length=30, blank=True, default="")

    class Meta:
        verbose_name = "Centre de santé"
        verbose_name_plural = "Centres de santé"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.commune})"


class Agent(models.Model):
    """Compte agent rattaché à un utilisateur Django et à un centre de santé."""

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent",
        verbose_name="Utilisateur",
    )
    centre = models.ForeignKey(
        Centre,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="agents",
        verbose_name="Centre de santé",
    )
    fonction = models.CharField(
        "Fonction",
        max_length=120,
        blank=True,
        default="Agent vaccinateur",
    )

    class Meta:
        verbose_name = "Agent"
        verbose_name_plural = "Agents"
        ordering = ["utilisateur__username"]

    def __str__(self):
        nom_affiche = self.utilisateur.get_full_name() or self.utilisateur.username
        if self.centre:
            return f"{nom_affiche} - {self.centre.nom}"
        return f"{nom_affiche} (sans centre)"


class Enfant(models.Model):
    """Fiche administrative d'un enfant inscrit au registre vaccinal du centre."""

    SEXE_CHOIX = [
        ("M", "Masculin"),
        ("F", "Féminin"),
    ]

    centre = models.ForeignKey(
        Centre,
        on_delete=models.CASCADE,
        related_name="enfants",
        verbose_name="Centre de santé",
    )
    numero = models.CharField(
        "Numéro du registre papier",
        max_length=50,
    )
    nom = models.CharField("Nom", max_length=100)
    prenom = models.CharField("Prénom", max_length=100)
    sexe = models.CharField("Sexe", max_length=1, choices=SEXE_CHOIX)
    date_naissance = models.DateField("Date de naissance")
    nom_mere = models.CharField("Nom de la mère", max_length=150)
    telephone = models.CharField("Téléphone", max_length=30, blank=True, default="")
    quartier = models.CharField("Quartier ou village", max_length=120, blank=True, default="")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enfants_crees",
        verbose_name="Créé par",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Enfant"
        verbose_name_plural = "Enfants"
        ordering = ["nom", "prenom", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["centre", "numero"],
                name="unique_numero_par_centre",
            )
        ]

    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.numero})"

    def doses_recues(self):
        """Retourne un dictionnaire {clé_vaccin: date_administration}."""
        return {dose.cle: dose.date_administration for dose in self.doses.all()}


class Dose(models.Model):
    """Enregistrement administratif d'une dose administrée à un enfant."""

    CLES_CHOIX = [(entree["cle"], entree["nom"]) for entree in CALENDRIER_PEV]

    enfant = models.ForeignKey(
        Enfant,
        on_delete=models.CASCADE,
        related_name="doses",
        verbose_name="Enfant",
    )
    cle = models.CharField("Clé du vaccin", max_length=30, choices=CLES_CHOIX)
    date_administration = models.DateField("Date d'administration")
    lot = models.CharField("Numéro de lot", max_length=60, blank=True, default="")
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doses_saisies",
        verbose_name="Agent",
    )
    date_saisie = models.DateTimeField("Date de saisie", auto_now_add=True)

    class Meta:
        verbose_name = "Dose administrée"
        verbose_name_plural = "Doses administrées"
        ordering = ["-date_administration", "cle"]
        constraints = [
            models.UniqueConstraint(
                fields=["enfant", "cle"],
                name="unique_dose_par_enfant",
            )
        ]

    def __str__(self):
        return f"{self.enfant} - {self.nom_dose()} ({self.date_administration})"

    def nom_dose(self):
        """Retourne le libellé du calendrier correspondant à la clé de la dose."""
        entree = CALENDRIER_PAR_CLE.get(self.cle)
        return entree["nom"] if entree else self.cle
