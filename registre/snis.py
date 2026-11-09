"""Production locale du rapport de séance au format d'import DHIS2.

Ce module prépare les agrégations et les fichiers d'import (JSON et CSV)
sans jamais effectuer d'envoi ni de connexion réseau sortante.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
import io

from .calendrier import (
    CALENDRIER_PAR_CLE,
    ORDRE_PAR_CLE,
    age_en_mois,
    normaliser_cle,
)

JEU_DE_DONNEES = "PEV_SEANCE_VACCINATION"
AGE_MOINS_1_AN = "MOINS_1_AN"
AGE_1_AN_ET_PLUS = "1_AN_ET_PLUS"

# Les identifiants techniques DHIS2 (UID de 11 caractères pour les éléments de
# données, combinaisons d'options de catégorie et unités d'organisation) sont
# propres à chaque instance DHIS2 et ne doivent pas être inventés.
# Ce dictionnaire reste volontairement vide et peut être complété localement
# selon le paramétrage de l'instance cible.
CORRESPONDANCE_UID: dict[str, str] = {}


def _en_date(valeur: date | datetime) -> date:
    if isinstance(valeur, datetime):
        return valeur.date()
    return valeur


def tranche_age(date_naissance: date, date_administration: date) -> str:
    """Calcule la tranche d'âge (< 1 an ou >= 1 an) à la date d'administration."""
    mois = age_en_mois(_en_date(date_naissance), _en_date(date_administration))
    if mois < 12:
        return AGE_MOINS_1_AN
    return AGE_1_AN_ET_PLUS


def code_element(cle: str) -> str:
    """Retourne le code élément DHIS2 sous la forme PEV_<CLE EN MAJUSCULES>."""
    cle_norm = normaliser_cle(cle)
    return f"PEV_{cle_norm.upper()}"


def code_unite(centre) -> str:
    """Retourne le code FOSA du centre ou un identifiant provisoire distinct."""
    code = (getattr(centre, "code_fosa", "") or "").strip()
    if code:
        return code
    return f"BJ-FOSA-PROVISOIRE-{centre.pk}"


def _libelle_agent(agent) -> str:
    if agent is None:
        return "non précisé"
    if isinstance(agent, str):
        return agent
    if hasattr(agent, "utilisateur"):
        return agent.utilisateur.get_full_name() or agent.utilisateur.username
    if hasattr(agent, "get_full_name"):
        return agent.get_full_name() or agent.username
    return str(agent)


def agreger(doses, jour: date) -> list[dict]:
    """Agrège les doses administrées à la date donnée par antigène et tranche d'âge."""
    jour_cible = _en_date(jour)
    compteurs: dict[str, dict[str, int]] = {}

    for dose in doses:
        date_admin = _en_date(dose.date_administration)
        if date_admin != jour_cible:
            continue
        cle = normaliser_cle(dose.cle)
        if cle not in CALENDRIER_PAR_CLE:
            continue
        tranche = tranche_age(dose.enfant.date_naissance, date_admin)
        if cle not in compteurs:
            compteurs[cle] = {
                AGE_MOINS_1_AN: 0,
                AGE_1_AN_ET_PLUS: 0,
            }
        compteurs[cle][tranche] += 1

    lignes = []
    for cle in sorted(compteurs.keys(), key=lambda c: ORDRE_PAR_CLE.get(c, 999)):
        moins_1_an = compteurs[cle][AGE_MOINS_1_AN]
        un_an_et_plus = compteurs[cle][AGE_1_AN_ET_PLUS]
        entree = CALENDRIER_PAR_CLE[cle]
        lignes.append(
            {
                "cle": cle,
                "nom": entree["nom"],
                "code_element": code_element(cle),
                "moins_1_an": moins_1_an,
                "un_an_et_plus": un_an_et_plus,
                "total": moins_1_an + un_an_et_plus,
            }
        )
    return lignes


def payload(centre, lignes: list[dict], jour: date, agent=None) -> dict:
    """Construit la structure JSON dataValueSets attendue par DHIS2."""
    jour_cible = _en_date(jour)
    periode = jour_cible.strftime("%Y%m%d")
    unite = code_unite(centre)
    nom_agent = _libelle_agent(agent)

    valeurs: list[dict] = []
    for ligne in lignes:
        tranches = [
            (AGE_MOINS_1_AN, "moins de 1 an", ligne.get("moins_1_an", 0)),
            (AGE_1_AN_ET_PLUS, "1 an et plus", ligne.get("un_an_et_plus", 0)),
        ]
        for code_tranche, libelle_tranche, compte in tranches:
            if compte > 0:
                valeurs.append(
                    {
                        "dataElement": ligne["code_element"],
                        "period": periode,
                        "orgUnit": unite,
                        "categoryOptionCombo": code_tranche,
                        "value": str(compte),
                        "comment": (
                            f"{ligne['nom']} ({libelle_tranche}) - "
                            f"saisi par {nom_agent}"
                        ),
                    }
                )

    return {
        "dataSet": JEU_DE_DONNEES,
        "completeDate": jour_cible.isoformat(),
        "period": periode,
        "orgUnit": unite,
        "dataElementIdScheme": "CODE",
        "orgUnitIdScheme": "CODE",
        "dataValues": valeurs,
    }


def generer_csv(centre, lignes: list[dict], jour: date, agent=None) -> str:
    """Génère le contenu CSV d'import DHIS2 correspondant au rapport de séance."""
    doc = payload(centre, lignes, jour, agent)
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon)
    ecrivain.writerow(
        [
            "dataElement",
            "period",
            "orgUnit",
            "categoryOptionCombo",
            "value",
            "comment",
        ]
    )
    for item in doc["dataValues"]:
        ecrivain.writerow(
            [
                item["dataElement"],
                item["period"],
                item["orgUnit"],
                item["categoryOptionCombo"],
                item["value"],
                item["comment"],
            ]
        )
    return tampon.getvalue()
