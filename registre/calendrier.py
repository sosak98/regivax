"""Calendrier vaccinal de référence utilisé par RegiVax.

Sources : PEV Bénin et DNPEV-SSP pour le socle BCG, VPO, Penta, PCV-13, VAR et VAA ;
rotavirus introduit en décembre 2019 ; VPI à 14 semaines ; RTS,S introduit en avril 2024 ;
deuxième dose rougeole-rubéole introduite en décembre 2024 à 18 mois.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
import re
import unicodedata

INTERVALLE_MIN_SEMAINES = 4
AGE_LIMITE_RATTRAPAGE_MOIS = 59

STATUT_RECU = "Reçu"
STATUT_MATERNITE = "À la maternité"
STATUT_EN_RETARD = "En retard"
STATUT_AUJOURDHUI = "Aujourd'hui"
STATUT_A_VENIR = "À venir"

CALENDRIER_PEV = [
    {
        "cle": "bcg",
        "nom": "BCG",
        "dose": 1,
        "serie": "bcg",
        "age_semaines": 0,
        "affichage": "Naissance",
        "maladies": "Tuberculose",
        "voie": "Intradermique, bras droit",
    },
    {
        "cle": "vpo_0",
        "nom": "VPO 0",
        "dose": 1,
        "serie": "vpo_naissance",
        "age_semaines": 0,
        "affichage": "Naissance",
        "maladies": "Poliomyélite",
        "voie": "Orale, 2 gouttes",
    },
    {
        "cle": "hepb_0",
        "nom": "Hépatite B (dose naissance)",
        "dose": 1,
        "serie": "hepb_naissance",
        "age_semaines": 0,
        "affichage": "Naissance",
        "maladies": "Hépatite B",
        "voie": "Intramusculaire, cuisse",
        "maternite": True,
    },
    {
        "cle": "penta_1",
        "nom": "Pentavalent 1",
        "dose": 1,
        "serie": "penta",
        "age_semaines": 6,
        "affichage": "6 semaines",
        "maladies": "Diphtérie, tétanos, coqueluche, hépatite B, Haemophilus influenzae b",
        "voie": "Intramusculaire, face externe de la cuisse",
    },
    {
        "cle": "vpo_1",
        "nom": "VPO 1",
        "dose": 1,
        "serie": "vpo",
        "age_semaines": 6,
        "affichage": "6 semaines",
        "maladies": "Poliomyélite",
        "voie": "Orale, 2 gouttes",
    },
    {
        "cle": "pcv_1",
        "nom": "PCV-13 1",
        "dose": 1,
        "serie": "pcv",
        "age_semaines": 6,
        "affichage": "6 semaines",
        "maladies": "Infections à pneumocoque (pneumonie, méningite, otite)",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "rota_1",
        "nom": "Rotavirus 1",
        "dose": 1,
        "serie": "rota",
        "age_semaines": 6,
        "affichage": "6 semaines",
        "maladies": "Diarrhées sévères à rotavirus",
        "voie": "Orale",
    },
    {
        "cle": "penta_2",
        "nom": "Pentavalent 2",
        "dose": 2,
        "serie": "penta",
        "age_semaines": 10,
        "affichage": "10 semaines",
        "maladies": "Diphtérie, tétanos, coqueluche, hépatite B, Haemophilus influenzae b",
        "voie": "Intramusculaire, face externe de la cuisse",
    },
    {
        "cle": "vpo_2",
        "nom": "VPO 2",
        "dose": 2,
        "serie": "vpo",
        "age_semaines": 10,
        "affichage": "10 semaines",
        "maladies": "Poliomyélite",
        "voie": "Orale, 2 gouttes",
    },
    {
        "cle": "pcv_2",
        "nom": "PCV-13 2",
        "dose": 2,
        "serie": "pcv",
        "age_semaines": 10,
        "affichage": "10 semaines",
        "maladies": "Infections à pneumocoque",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "rota_2",
        "nom": "Rotavirus 2",
        "dose": 2,
        "serie": "rota",
        "age_semaines": 10,
        "affichage": "10 semaines",
        "maladies": "Diarrhées sévères à rotavirus",
        "voie": "Orale",
    },
    {
        "cle": "penta_3",
        "nom": "Pentavalent 3",
        "dose": 3,
        "serie": "penta",
        "age_semaines": 14,
        "affichage": "14 semaines",
        "maladies": "Diphtérie, tétanos, coqueluche, hépatite B, Haemophilus influenzae b",
        "voie": "Intramusculaire, face externe de la cuisse",
    },
    {
        "cle": "pcv_3",
        "nom": "PCV-13 3",
        "dose": 3,
        "serie": "pcv",
        "age_semaines": 14,
        "affichage": "14 semaines",
        "maladies": "Infections à pneumocoque",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "rota_3",
        "nom": "Rotavirus 3",
        "dose": 3,
        "serie": "rota",
        "age_semaines": 14,
        "affichage": "14 semaines",
        "maladies": "Diarrhées sévères à rotavirus",
        "voie": "Orale",
    },
    {
        "cle": "vpi",
        "nom": "VPI (polio injectable)",
        "dose": 1,
        "serie": "vpi",
        "age_semaines": 14,
        "affichage": "14 semaines",
        "maladies": "Poliomyélite",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "rtss_1",
        "nom": "Antipaludique 1 (RTS,S)",
        "dose": 1,
        "serie": "rtss",
        "age_mois": 6,
        "affichage": "6 mois",
        "maladies": "Paludisme (formes graves à Plasmodium falciparum)",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "vit_a_1",
        "nom": "Vitamine A (1re dose)",
        "dose": 1,
        "serie": "vitamine_a",
        "age_mois": 6,
        "affichage": "6 mois",
        "maladies": "Carence en vitamine A",
        "voie": "Orale, capsule 100 000 UI",
        "categorie": "supplementation",
    },
    {
        "cle": "rtss_2",
        "nom": "Antipaludique 2 (RTS,S)",
        "dose": 2,
        "serie": "rtss",
        "age_mois": 7,
        "affichage": "7 mois",
        "maladies": "Paludisme",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "var_1",
        "nom": "VAR 1 (rougeole-rubéole)",
        "dose": 1,
        "serie": "var",
        "age_mois": 9,
        "affichage": "9 mois",
        "maladies": "Rougeole, rubéole",
        "voie": "Sous-cutanée, bras",
    },
    {
        "cle": "vaa",
        "nom": "VAA (fièvre jaune)",
        "dose": 1,
        "serie": "vaa",
        "age_mois": 9,
        "affichage": "9 mois",
        "maladies": "Fièvre jaune",
        "voie": "Sous-cutanée, bras",
    },
    {
        "cle": "mena",
        "nom": "MenA (méningite A)",
        "dose": 1,
        "serie": "mena",
        "age_mois": 9,
        "affichage": "9 mois",
        "maladies": "Méningite à méningocoque A",
        "voie": "Intramusculaire, bras",
    },
    {
        "cle": "rtss_3",
        "nom": "Antipaludique 3 (RTS,S)",
        "dose": 3,
        "serie": "rtss",
        "age_mois": 9,
        "affichage": "9 mois",
        "maladies": "Paludisme",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "vit_a_2",
        "nom": "Vitamine A (2e dose)",
        "dose": 2,
        "serie": "vitamine_a",
        "age_mois": 12,
        "affichage": "12 mois",
        "maladies": "Carence en vitamine A",
        "voie": "Orale, capsule 200 000 UI",
        "categorie": "supplementation",
    },
    {
        "cle": "var_2",
        "nom": "VAR 2 (rappel rougeole-rubéole)",
        "dose": 2,
        "serie": "var",
        "age_mois": 18,
        "affichage": "18 mois",
        "maladies": "Rougeole, rubéole",
        "voie": "Sous-cutanée, bras",
    },
    {
        "cle": "rtss_4",
        "nom": "Antipaludique 4 (RTS,S)",
        "dose": 4,
        "serie": "rtss",
        "age_mois": 18,
        "affichage": "18 mois",
        "maladies": "Paludisme",
        "voie": "Intramusculaire, cuisse",
    },
    {
        "cle": "vit_a_3",
        "nom": "Vitamine A (3e dose)",
        "dose": 3,
        "serie": "vitamine_a",
        "age_mois": 18,
        "affichage": "18 mois",
        "maladies": "Carence en vitamine A",
        "voie": "Orale, capsule 200 000 UI",
        "categorie": "supplementation",
    },
]

CALENDRIER_PAR_CLE = {entree["cle"]: entree for entree in CALENDRIER_PEV}
ORDRE_PAR_CLE = {entree["cle"]: idx for idx, entree in enumerate(CALENDRIER_PEV)}


def _nettoyer_chaine(valeur: str) -> str:
    decomposition = unicodedata.normalize("NFKD", str(valeur).strip().lower())
    sans_accents = "".join(
        c for c in decomposition if not unicodedata.combining(c)
    )
    remplace = re.sub(r"[^a-z0-9]+", "_", sans_accents)
    return remplace.strip("_")


_ALIAS_CLES = {
    _nettoyer_chaine(entree["nom"]): entree["cle"] for entree in CALENDRIER_PEV
}
_ALIAS_CLES.update(
    {
        "vpo0": "vpo_0",
        "vpo1": "vpo_1",
        "vpo2": "vpo_2",
        "hepb0": "hepb_0",
        "hepatite_b_0": "hepb_0",
        "hepatite_b_naissance": "hepb_0",
        "penta1": "penta_1",
        "penta2": "penta_2",
        "penta3": "penta_3",
        "pentavalent_1": "penta_1",
        "pentavalent_2": "penta_2",
        "pentavalent_3": "penta_3",
        "pcv13_1": "pcv_1",
        "pcv_13_1": "pcv_1",
        "pcv13_2": "pcv_2",
        "pcv_13_2": "pcv_2",
        "pcv13_3": "pcv_3",
        "pcv_13_3": "pcv_3",
        "rotavirus_1": "rota_1",
        "rotavirus_2": "rota_2",
        "rotavirus_3": "rota_3",
        "vpi_polio_injectable": "vpi",
        "rtss1": "rtss_1",
        "rtss2": "rtss_2",
        "rtss3": "rtss_3",
        "rtss4": "rtss_4",
        "rts_s_1": "rtss_1",
        "rts_s_2": "rtss_2",
        "rts_s_3": "rtss_3",
        "rts_s_4": "rtss_4",
        "vitamine_a_1": "vit_a_1",
        "vitamine_a_2": "vit_a_2",
        "vitamine_a_3": "vit_a_3",
        "var1": "var_1",
        "var2": "var_2",
        "var_1_rougeole_rubeole": "var_1",
        "var_2_rappel_rougeole_rubeole": "var_2",
        "vaa_fievre_jaune": "vaa",
        "mena_meningite_a": "mena",
    }
)


def _en_date(valeur: date | datetime) -> date:
    if isinstance(valeur, datetime):
        return valeur.date()
    return valeur


def _ajouter_mois(depart: date, mois: int) -> date:
    total_mois = depart.month - 1 + mois
    annee = depart.year + total_mois // 12
    mois_cible = total_mois % 12 + 1
    dernier_jour = calendar.monthrange(annee, mois_cible)[1]
    return date(annee, mois_cible, min(depart.day, dernier_jour))


def normaliser_cle(nom: str | None) -> str:
    """Normalise un nom ou identifiant de vaccin vers une clé canonique."""
    if not nom:
        return ""
    propre = _nettoyer_chaine(nom)
    if propre in CALENDRIER_PAR_CLE:
        return propre
    return _ALIAS_CLES.get(propre, propre)


def age_en_mois(date_naissance: date, reference: date | None = None) -> int:
    """Calcule l'âge en mois révolus à la date de référence."""
    naissance = _en_date(date_naissance)
    ref = _en_date(reference) if reference is not None else date.today()
    if ref <= naissance:
        return 0
    mois = (ref.year - naissance.year) * 12 + (ref.month - naissance.month)
    if ref.day < naissance.day:
        mois -= 1
    return max(0, mois)


def date_theorique(date_naissance: date, entree: dict | str) -> date:
    """Calcule la date théorique prévue pour une entrée du calendrier."""
    naissance = _en_date(date_naissance)
    if isinstance(entree, str):
        entree = CALENDRIER_PAR_CLE[normaliser_cle(entree)]
    if "age_semaines" in entree:
        return naissance + timedelta(weeks=entree["age_semaines"])
    if "age_mois" in entree:
        return _ajouter_mois(naissance, entree["age_mois"])
    raise ValueError(f"Entrée de calendrier sans âge cible valide : {entree}")


def planifier(
    date_naissance: date,
    vaccins_recus: dict[str, date] | None,
    aujourd_hui: date | None = None,
) -> list[dict]:
    """Planifie les 26 doses du calendrier et retourne la liste triée par date."""
    naissance = _en_date(date_naissance)
    ref = _en_date(aujourd_hui) if aujourd_hui is not None else date.today()

    recus_normalises: dict[str, date] = {}
    for cle_brute, date_recue in (vaccins_recus or {}).items():
        if date_recue is not None:
            recus_normalises[normaliser_cle(cle_brute)] = _en_date(date_recue)

    derniere_date_serie: dict[str, date] = {}
    resultat: list[dict] = []

    for entree in CALENDRIER_PEV:
        cle = entree["cle"]
        serie = entree["serie"]
        d_theo = date_theorique(naissance, entree)

        if cle in recus_normalises:
            date_prevue = recus_normalises[cle]
            statut = STATUT_RECU
            retard_jours = 0
        elif entree.get("maternite"):
            date_prevue = d_theo
            statut = STATUT_MATERNITE
            retard_jours = 0
        else:
            date_prevue = d_theo
            if serie in derniere_date_serie:
                date_min = derniere_date_serie[serie] + timedelta(
                    weeks=INTERVALLE_MIN_SEMAINES
                )
                if date_prevue < date_min:
                    date_prevue = date_min

            if date_prevue < ref:
                statut = STATUT_EN_RETARD
                retard_jours = (ref - date_prevue).days
            elif date_prevue == ref:
                statut = STATUT_AUJOURDHUI
                retard_jours = 0
            else:
                statut = STATUT_A_VENIR
                retard_jours = 0

        derniere_date_serie[serie] = date_prevue
        resultat.append(
            {
                "cle": cle,
                "nom": entree["nom"],
                "dose": entree["dose"],
                "serie": serie,
                "date_prevue": date_prevue,
                "statut": statut,
                "retard_jours": retard_jours,
                "maladies": entree["maladies"],
                "voie": entree["voie"],
                "age_affichage": entree["affichage"],
            }
        )

    resultat.sort(key=lambda item: (item["date_prevue"], ORDRE_PAR_CLE[item["cle"]]))
    return resultat


def _obtenir_planning(
    plan_ou_naissance: list[dict] | tuple[dict, ...] | date,
    vaccins_recus: dict[str, date] | None = None,
    aujourd_hui: date | None = None,
) -> list[dict]:
    if isinstance(plan_ou_naissance, (list, tuple)):
        return list(plan_ou_naissance)
    return planifier(plan_ou_naissance, vaccins_recus, aujourd_hui=aujourd_hui)


def prochain_rdv(
    plan_ou_naissance: list[dict] | tuple[dict, ...] | date,
    vaccins_recus: dict[str, date] | None = None,
    aujourd_hui: date | None = None,
) -> dict | None:
    """Retourne la dose en retard la plus ancienne, sinon la prochaine dose due."""
    planning = _obtenir_planning(plan_ou_naissance, vaccins_recus, aujourd_hui)
    en_retard = [d for d in planning if d["statut"] == STATUT_EN_RETARD]
    if en_retard:
        return min(
            en_retard,
            key=lambda d: (d["date_prevue"], ORDRE_PAR_CLE.get(d["cle"], 999)),
        )

    dues = [
        d
        for d in planning
        if d["statut"] in (STATUT_AUJOURDHUI, STATUT_A_VENIR)
    ]
    if dues:
        return min(
            dues,
            key=lambda d: (d["date_prevue"], ORDRE_PAR_CLE.get(d["cle"], 999)),
        )
    return None


def resume_couverture(
    plan_ou_naissance: list[dict] | tuple[dict, ...] | date,
    vaccins_recus: dict[str, date] | None = None,
    aujourd_hui: date | None = None,
) -> dict[str, int]:
    """Retourne les effectifs par statut pour l'ensemble du calendrier."""
    planning = _obtenir_planning(plan_ou_naissance, vaccins_recus, aujourd_hui)
    return {
        "total": len(planning),
        "recus": sum(1 for d in planning if d["statut"] == STATUT_RECU),
        "maternite": sum(1 for d in planning if d["statut"] == STATUT_MATERNITE),
        "en_retard": sum(1 for d in planning if d["statut"] == STATUT_EN_RETARD),
        "aujourd_hui": sum(1 for d in planning if d["statut"] == STATUT_AUJOURDHUI),
        "a_venir": sum(1 for d in planning if d["statut"] == STATUT_A_VENIR),
    }
