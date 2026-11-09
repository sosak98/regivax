"""Commande Django pour charger un jeu de démonstration reproductible."""

from datetime import date, timedelta
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from registre.calendrier import (
    CALENDRIER_PEV,
    INTERVALLE_MIN_SEMAINES,
    date_theorique,
)
from registre.models import Agent, Centre, Dose, Enfant

GRAINE_FIXE = 20261109

# Répartition du tirage : une minorité d'enfants sans aucune dose, une
# minorité parfaitement à jour, le reste avec une date de décrochage.
PROPORTION_SANS_DOSE = 0.10
PROPORTION_A_JOUR = 0.12
DECALAGE_MAX_ADMINISTRATION_JOURS = 10

NOMS_FAMILLE = [
    "Agossou",
    "Amoussou",
    "Assogba",
    "Boko",
    "Codjo",
    "Degla",
    "Dossou",
    "Gbaguidi",
    "Gbènakpon",
    "Hounsou",
    "Kpadonou",
    "Moussa",
    "Sossou",
    "Tossou",
    "Zinsou",
]

PRENOMS_FILLES = [
    "Adjoua",
    "Aïssatou",
    "Akouavi",
    "Fifamè",
    "Gbèkpon",
    "Mèdessè",
    "Rachidatou",
    "Sènan",
    "Tèko",
    "Yabo",
]

PRENOMS_GARCONS = [
    "Biodun",
    "Codjo",
    "Dègbé",
    "Houénou",
    "Koffi",
    "Kouassi",
    "Mawuli",
    "Sèdjro",
    "Sèna",
    "Tévi",
]

PRENOMS_MERES = [
    "Abibatou",
    "Afiavi",
    "Chantal",
    "Clarisse",
    "Dossi",
    "Edwige",
    "Estelle",
    "Félicité",
    "Hortense",
    "Julienne",
    "Nadine",
    "Pascaline",
    "Rosine",
    "Solange",
    "Véronique",
]

QUARTIERS = [
    "Secteur Nord (fictif)",
    "Secteur Sud (fictif)",
    "Secteur Est (fictif)",
    "Secteur Ouest (fictif)",
    "Secteur Centre (fictif)",
]

LOTS_FICTIFS = ["LOT-DEMO-A", "LOT-DEMO-B", "LOT-DEMO-C"]

TRANCHES_JOURS = (
    [(8, 35)] * 5
    + [(45, 95)] * 8
    + [(105, 180)] * 8
    + [(195, 345)] * 10
    + [(370, 700)] * 8
    + [(730, 1150)] * 6
)

# Quelques doses datées du jour, réparties dans les deux tranches d'âge du
# rapport de séance. Elles ne sont attribuées qu'à des enfants déjà vaccinés
# et seulement pour une dose dont la date théorique est déjà atteinte.
CIBLES_DU_JOUR = [
    ("penta_1", "moins_1_an"),
    ("vpo_1", "moins_1_an"),
    ("rtss_1", "moins_1_an"),
    ("var_1", "moins_1_an"),
    ("vaa", "moins_1_an"),
    ("bcg", "moins_1_an"),
    ("vit_a_2", "un_an_et_plus"),
    ("var_2", "un_an_et_plus"),
]


def _tirer_date_decrochage(rng: random.Random, naissance: date, aujourd_hui: date) -> date:
    """Tire la date de décrochage d'un enfant entre sa naissance et aujourd'hui.

    La valeur aujourd'hui + 1 jour représente le cas particulier d'un enfant
    parfaitement à jour : toutes les doses dont la date théorique est atteinte
    sont enregistrées. La valeur égale à la naissance représente le cas d'un
    enfant sans aucune dose.
    """
    tirage = rng.random()
    if tirage < PROPORTION_SANS_DOSE:
        return naissance
    if tirage < PROPORTION_SANS_DOSE + PROPORTION_A_JOUR:
        return aujourd_hui + timedelta(days=1)
    ecart = (aujourd_hui - naissance).days
    if ecart <= 0:
        return naissance
    return naissance + timedelta(days=rng.randint(1, ecart))


def _doses_a_creer(
    enfant: Enfant,
    date_decrochage: date,
    aujourd_hui: date,
    rng: random.Random,
    agent,
) -> list[Dose]:
    """Construit les doses d'un enfant selon la règle de la date de décrochage.

    Toutes les doses dont la date théorique précède la date de décrochage sont
    retenues, aucune de celles qui la suivent. Les dates d'administration sont
    calculées par ordre chronologique de date théorique et restent croissantes,
    afin qu'aucune dose postérieure ne précède une dose absente.
    """
    retenues: list[tuple[date, dict]] = []
    for entree in CALENDRIER_PEV:
        d_theo = date_theorique(enfant.date_naissance, entree)
        if d_theo >= date_decrochage:
            continue
        if d_theo > aujourd_hui:
            continue
        retenues.append((d_theo, entree))

    retenues.sort(key=lambda item: item[0])

    doses: list[Dose] = []
    derniere_date_globale: date | None = None
    derniere_date_serie: dict[str, date] = {}

    for d_theo, entree in retenues:
        serie = entree["serie"]
        if entree.get("age_semaines") == 0 or entree.get("maternite"):
            date_admin = d_theo
        else:
            date_admin = d_theo + timedelta(
                days=rng.randint(0, DECALAGE_MAX_ADMINISTRATION_JOURS)
            )
            if date_admin > aujourd_hui:
                date_admin = aujourd_hui

        # La date d'administration ne peut pas remonter avant la dose qui la
        # précède, ni avant l'intervalle minimal de la même série.
        if derniere_date_globale is not None and date_admin < derniere_date_globale:
            date_admin = derniere_date_globale
        if serie in derniere_date_serie:
            date_min_serie = derniere_date_serie[serie] + timedelta(
                weeks=INTERVALLE_MIN_SEMAINES
            )
            if date_admin < date_min_serie:
                date_admin = date_min_serie
        if date_admin > aujourd_hui:
            date_admin = aujourd_hui
        if date_admin < d_theo:
            date_admin = d_theo

        derniere_date_globale = date_admin
        derniere_date_serie[serie] = date_admin
        doses.append(
            Dose(
                enfant=enfant,
                cle=entree["cle"],
                date_administration=date_admin,
                lot=rng.choice(LOTS_FICTIFS),
                agent=agent,
            )
        )

    return doses


class Command(BaseCommand):
    """Charge un centre fictif, le compte agent.demo et 45 enfants fictifs."""

    help = "Charge le jeu de démonstration fictif et reproductible de RegiVax."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reinitialiser",
            action="store_true",
            help="Supprime et recrée les enfants fictifs du centre de démonstration.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        aujourd_hui = date.today()
        rng = random.Random(GRAINE_FIXE)

        centre, _ = Centre.objects.get_or_create(
            nom="Centre de santé de démonstration (fictif)",
            defaults={
                "commune": "Commune fictive",
                "zone_sanitaire": "Zone sanitaire de démonstration",
                "code_fosa": "",
                "telephone": "",
            },
        )

        utilisateur, _ = User.objects.get_or_create(
            username="agent.demo",
            defaults={
                "first_name": "Agent",
                "last_name": "Démonstration",
                "is_active": True,
            },
        )
        utilisateur.set_password("demonstration2026")
        utilisateur.save()

        Agent.objects.get_or_create(
            utilisateur=utilisateur,
            defaults={
                "centre": centre,
                "fonction": "Agent vaccinateur (démonstration)",
            },
        )

        if options.get("reinitialiser"):
            Enfant.objects.filter(centre=centre).delete()

        if Enfant.objects.filter(centre=centre).exists():
            self.stdout.write(
                self.style.NOTICE(
                    "Le jeu de démonstration est déjà présent dans ce centre."
                )
            )
            return

        enfants_crees: list[tuple[Enfant, int]] = []
        for idx, (age_min_j, age_max_j) in enumerate(TRANCHES_JOURS, start=1):
            sexe = "F" if idx % 2 == 1 else "M"
            nom = rng.choice(NOMS_FAMILLE)
            prenom = (
                rng.choice(PRENOMS_FILLES)
                if sexe == "F"
                else rng.choice(PRENOMS_GARCONS)
            )
            nom_mere = f"{rng.choice(NOMS_FAMILLE)} {rng.choice(PRENOMS_MERES)}"
            age_jours = rng.randint(age_min_j, age_max_j)
            date_naissance = aujourd_hui - timedelta(days=age_jours)

            enfant = Enfant.objects.create(
                centre=centre,
                numero=f"RV-DEMO-{idx:03d}",
                nom=nom,
                prenom=prenom,
                sexe=sexe,
                date_naissance=date_naissance,
                nom_mere=nom_mere,
                telephone="",
                quartier=rng.choice(QUARTIERS),
                cree_par=utilisateur,
            )
            enfants_crees.append((enfant, age_jours))

        total_doses = 0
        for enfant, _age_jours in enfants_crees:
            date_decrochage = _tirer_date_decrochage(
                rng, enfant.date_naissance, aujourd_hui
            )
            doses = _doses_a_creer(
                enfant, date_decrochage, aujourd_hui, rng, utilisateur
            )
            if doses:
                Dose.objects.bulk_create(doses)
            total_doses += len(doses)

        # Doses datées du jour pour que le rapport de séance ne soit jamais vide.
        # Elles sont attribuées à des enfants déjà vaccinés, sans écraser une
        # dose existante et sans créer de trou avant une dose déjà saisie.
        enfants_deja_cibles: set[int] = set()
        for cle_cible, tranche in CIBLES_DU_JOUR:
            entree_cible = next(e for e in CALENDRIER_PEV if e["cle"] == cle_cible)
            candidat = None
            for enfant, age_jours in enfants_crees:
                if enfant.pk in enfants_deja_cibles:
                    continue
                if tranche == "moins_1_an" and age_jours >= 365:
                    continue
                if tranche == "un_an_et_plus" and age_jours < 365:
                    continue
                d_theo = date_theorique(enfant.date_naissance, entree_cible)
                if d_theo > aujourd_hui:
                    continue
                doses_enfant = list(Dose.objects.filter(enfant=enfant))
                if any(d.cle == cle_cible for d in doses_enfant):
                    continue
                if not any(d.cle == "bcg" for d in doses_enfant):
                    continue
                # La dose du jour doit être la plus récente du calendrier pour
                # cet enfant : aucune dose déjà saisie ne doit la suivre.
                dates_presentes = [
                    date_theorique(
                        enfant.date_naissance, next(e for e in CALENDRIER_PEV if e["cle"] == d.cle)
                    )
                    for d in doses_enfant
                ]
                if dates_presentes and max(dates_presentes) > d_theo:
                    continue
                candidat = enfant
                break

            if candidat is None:
                continue

            Dose.objects.create(
                enfant=candidat,
                cle=cle_cible,
                date_administration=aujourd_hui,
                lot="LOT-DEMO-JOUR",
                agent=utilisateur,
            )
            enfants_deja_cibles.add(candidat.pk)
            total_doses += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Jeu de démonstration chargé : 1 centre fictif, "
                f"{len(enfants_crees)} enfants et {total_doses} doses."
            )
        )
