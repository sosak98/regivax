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
    "Secteur Centre (fictif)",
    "Secteur Est (fictif)",
    "Secteur Ouest (fictif)",
]

TRANCHES_JOURS = (
    [(8, 35)] * 5
    + [(45, 95)] * 8
    + [(105, 180)] * 8
    + [(195, 345)] * 10
    + [(370, 700)] * 8
    + [(730, 1150)] * 6
)


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

        enfants_crees = []
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

        lots_fictifs = ["LOT-DEMO-A", "LOT-DEMO-B", "LOT-DEMO-C"]
        total_doses = 0

        for idx, (enfant, _age_jours) in enumerate(enfants_crees):
            derniere_par_serie = {}
            taux_progression = rng.uniform(0.45, 0.95)
            doses_a_creer = []

            for entree in CALENDRIER_PEV:
                cle = entree["cle"]
                serie = entree["serie"]
                d_theo = date_theorique(enfant.date_naissance, entree)

                if d_theo > aujourd_hui:
                    continue

                if entree.get("maternite"):
                    if rng.random() > 0.45:
                        continue
                    date_admin = enfant.date_naissance
                else:
                    if serie in derniere_par_serie:
                        date_min = derniere_par_serie[serie] + timedelta(
                            weeks=INTERVALLE_MIN_SEMAINES
                        )
                        if d_theo < date_min:
                            d_theo = date_min
                    if d_theo > aujourd_hui:
                        continue

                    decalage = rng.randint(0, 12)
                    date_admin = min(d_theo + timedelta(days=decalage), aujourd_hui)
                    if date_admin >= aujourd_hui:
                        date_admin = d_theo
                    if date_admin >= aujourd_hui:
                        continue
                    if rng.random() > taux_progression:
                        continue

                derniere_par_serie[serie] = date_admin
                doses_a_creer.append(
                    Dose(
                        enfant=enfant,
                        cle=cle,
                        date_administration=date_admin,
                        lot=rng.choice(lots_fictifs),
                        agent=utilisateur,
                    )
                )

            Dose.objects.bulk_create(doses_a_creer)
            total_doses += len(doses_a_creer)

        # Garantir plusieurs doses datées d'aujourd'hui chez des enfants de moins d'un an
        # et d'un an et plus afin que le rapport de séance du jour ne soit jamais vide.
        cibles_jour = [
            (0, "bcg", False),
            (6, "penta_1", False),
            (6, "vpo_1", False),
            (15, "rtss_1", False),
            (22, "var_1", False),
            (22, "vaa", False),
            (32, "vit_a_2", True),
            (39, "var_2", True),
        ]
        for index_defaut, cle_cible, un_an_ou_plus in cibles_jour:
            candidat = None
            for enfant_cand, age_j in enfants_crees:
                if un_an_ou_plus and age_j < 370:
                    continue
                if not un_an_ou_plus and age_j >= 365:
                    continue
                d_theo_cand = date_theorique(
                    enfant_cand.date_naissance,
                    next(e for e in CALENDRIER_PEV if e["cle"] == cle_cible),
                )
                if d_theo_cand > aujourd_hui:
                    continue
                if not Dose.objects.filter(enfant=enfant_cand, cle=cle_cible).exists():
                    candidat = enfant_cand
                    break
            if candidat is None:
                candidat, _ = enfants_crees[index_defaut]
            dose_obj, cree = Dose.objects.update_or_create(
                enfant=candidat,
                cle=cle_cible,
                defaults={
                    "date_administration": aujourd_hui,
                    "lot": "LOT-DEMO-JOUR",
                    "agent": utilisateur,
                },
            )
            if cree:
                total_doses += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Jeu de démonstration chargé : 1 centre fictif, "
                f"{len(enfants_crees)} enfants et {total_doses} doses."
            )
        )
