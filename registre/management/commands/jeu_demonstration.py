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

        # Nouvelle règle de génération par enfant : tirage d'une date de décrochage
        # comprise entre la naissance et aujourd'hui. Toutes les doses dont la
        # date théorique précède strictement cette date sont enregistrées, aucune
        # de celles qui la suivent ne l'est. Cela garantit la cohérence chronologique :
        # les doses de naissance (BCG, VPO 0) sont toujours présentes dès que l'enfant
        # a au moins une dose. Une minorité d'enfants est laissée sans aucune dose
        # (décrochage à la naissance) et une minorité est maintenue parfaitement à jour
        # (décrochage au lendemain de la date du jour) pour conserver la diversité.
        for enfant, age_jours in enfants_crees:
            # Tirage de la date de décrochage
            r = rng.random()
            if r < 0.10:
                # Minorité sans aucune dose : décrochage exactement à la naissance
                date_decrochage = enfant.date_naissance
            elif r < 0.22:
                # Minorité parfaitement à jour : décrochage au lendemain, inclut toutes les doses dues
                date_decrochage = aujourd_hui + timedelta(days=1)
            else:
                # Cas général : date aléatoire entre naissance+1 jour et aujourd'hui inclus
                decalage_decrochage = rng.randint(1, age_jours)
                date_decrochage = enfant.date_naissance + timedelta(days=decalage_decrochage)

            derniere_par_serie = {}
            doses_a_creer = []

            for entree in CALENDRIER_PEV:
                cle = entree["cle"]
                raw_d_theo = date_theorique(enfant.date_naissance, entree)

                # On n'enregistre que les doses dont la date théorique précède strictement la date de décrochage
                if raw_d_theo >= date_decrochage:
                    continue
                # Par construction raw_d_theo < date_decrochage <= aujourd_hui+1, donc
                # raw_d_theo <= aujourd_hui pour les cas généraux. On garde le garde-fou
                # pour les enfants très jeunes dont certaines doses sont encore futures.
                if raw_d_theo > aujourd_hui:
                    continue

                # Détermination de la date d'administration
                if entree.get("maternite") or entree.get("age_semaines") == 0:
                    # Doses de naissance : administrées à la naissance
                    date_admin = enfant.date_naissance
                else:
                    # Respect de l'intervalle minimal de 4 semaines dans la même série
                    d_theo_eff = raw_d_theo
                    serie = entree["serie"]
                    if serie in derniere_par_serie:
                        date_min = derniere_par_serie[serie] + timedelta(
                            weeks=INTERVALLE_MIN_SEMAINES
                        )
                        if d_theo_eff < date_min:
                            d_theo_eff = date_min
                        if d_theo_eff > aujourd_hui:
                            continue
                        if d_theo_eff >= date_decrochage:
                            # Si l'ajustement pousse la date au-delà du décrochage, on conserve
                            # la règle brute : la dose aurait dû être avant le décrochage, on l'inclut
                            # tout de même avec la date effective ajustée, sauf si elle devient future.
                            pass
                    decalage = rng.randint(0, 12)
                    # Première tentative : d_theo_eff + décalage, plafonnée à aujourd'hui
                    date_admin_candidate = min(
                        d_theo_eff + timedelta(days=decalage), aujourd_hui
                    )
                    if date_admin_candidate >= aujourd_hui:
                        # Si le plafond est atteint (dose due aujourd'hui), on retombe sur la date théorique
                        date_admin = d_theo_eff
                    else:
                        date_admin = date_admin_candidate
                    if date_admin >= aujourd_hui:
                        continue

                derniere_par_serie[entree["serie"]] = date_admin
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
        # Pour préserver la cohérence du jeu (BCG présent dès la première dose) et la
        # minorité d'enfants sans aucune dose, les doses non-BCG ne sont attribuées
        # qu'à des enfants possédant déjà le BCG.
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
                if Dose.objects.filter(enfant=enfant_cand, cle=cle_cible).exists():
                    continue
                # Préserver la règle BCG : aucune dose non-BCG n'est ajoutée à un enfant sans BCG
                if cle_cible != "bcg":
                    if not Dose.objects.filter(enfant=enfant_cand, cle="bcg").exists():
                        continue
                candidat = enfant_cand
                break
            if candidat is None:
                # Recherche d'un repli respectant les mêmes contraintes d'âge et de BCG
                for offset in range(len(enfants_crees)):
                    idx_repli = (index_defaut + offset) % len(enfants_crees)
                    enfant_repli, age_j_repli = enfants_crees[idx_repli]
                    if un_an_ou_plus and age_j_repli < 370:
                        continue
                    if not un_an_ou_plus and age_j_repli >= 365:
                        continue
                    d_theo_repli = date_theorique(
                        enfant_repli.date_naissance,
                        next(e for e in CALENDRIER_PEV if e["cle"] == cle_cible),
                    )
                    if d_theo_repli > aujourd_hui:
                        continue
                    if cle_cible != "bcg":
                        if not Dose.objects.filter(enfant=enfant_repli, cle="bcg").exists():
                            continue
                    candidat = enfant_repli
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
