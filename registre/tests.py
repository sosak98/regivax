"""Suite de tests automatisés pour RegiVax."""

import ast
import csv
from datetime import date, timedelta
import importlib
import io
import os
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from registre import calendrier, snis
from registre.apercu import est_mode_apercu
from registre.models import Agent, Centre, Dose, Enfant


class TestCalendrier(TestCase):
    """Tests du module autonome calendrier.py."""

    def test_26_entrees_et_unicite_des_cles(self):
        self.assertEqual(len(calendrier.CALENDRIER_PEV), 26)
        cles = [entree["cle"] for entree in calendrier.CALENDRIER_PEV]
        self.assertEqual(len(cles), len(set(cles)))

    def test_constantes_calendrier(self):
        self.assertEqual(calendrier.INTERVALLE_MIN_SEMAINES, 4)
        self.assertEqual(calendrier.AGE_LIMITE_RATTRAPAGE_MOIS, 59)

    def test_attributs_maternite_et_supplementation(self):
        self.assertTrue(calendrier.CALENDRIER_PAR_CLE["hepb_0"].get("maternite"))
        for cle_vit in ("vit_a_1", "vit_a_2", "vit_a_3"):
            self.assertEqual(
                calendrier.CALENDRIER_PAR_CLE[cle_vit].get("categorie"),
                "supplementation",
            )

    def test_normaliser_cle(self):
        self.assertEqual(calendrier.normaliser_cle("BCG"), "bcg")
        self.assertEqual(calendrier.normaliser_cle("  vpo-1 "), "vpo_1")
        self.assertEqual(calendrier.normaliser_cle("Pentavalent 2"), "penta_2")
        self.assertEqual(calendrier.normaliser_cle("Vitamine A (1re dose)"), "vit_a_1")
        self.assertEqual(calendrier.normaliser_cle("clé inconnue"), "cle_inconnue")

    def test_age_en_mois(self):
        naissance = date(2025, 1, 31)
        self.assertEqual(calendrier.age_en_mois(naissance, date(2025, 1, 31)), 0)
        self.assertEqual(calendrier.age_en_mois(naissance, date(2025, 7, 30)), 5)
        self.assertEqual(calendrier.age_en_mois(naissance, date(2025, 7, 31)), 6)
        self.assertEqual(calendrier.age_en_mois(naissance, date(2024, 12, 1)), 0)

    def test_date_theorique_semaines_et_mois(self):
        naissance = date(2025, 1, 31)
        self.assertEqual(
            calendrier.date_theorique(naissance, calendrier.CALENDRIER_PAR_CLE["penta_1"]),
            date(2025, 3, 14),
        )
        self.assertEqual(
            calendrier.date_theorique(date(2025, 8, 31), {"age_mois": 6}),
            date(2026, 2, 28),
        )

    def test_passage_dose_au_statut_recu(self):
        naissance = date(2026, 1, 1)
        aujourd_hui = date(2026, 3, 1)
        date_reelle = date(2026, 1, 3)

        plan = calendrier.planifier(
            naissance,
            {"bcg": date_reelle, "hepb_0": date(2026, 1, 1)},
            aujourd_hui=aujourd_hui,
        )
        par_cle = {item["cle"]: item for item in plan}
        self.assertEqual(par_cle["bcg"]["statut"], "Reçu")
        self.assertEqual(par_cle["bcg"]["date_prevue"], date_reelle)
        self.assertEqual(par_cle["bcg"]["retard_jours"], 0)
        self.assertEqual(par_cle["hepb_0"]["statut"], "Reçu")

    def test_statut_maternite_par_defaut(self):
        naissance = date(2026, 1, 1)
        plan = calendrier.planifier(naissance, {}, aujourd_hui=date(2026, 3, 1))
        par_cle = {item["cle"]: item for item in plan}
        self.assertEqual(par_cle["hepb_0"]["statut"], "À la maternité")

    def test_intervalle_minimal_quatre_semaines_meme_serie(self):
        naissance = date(2026, 1, 1)
        recus = {"penta_1": date(2026, 3, 26)}
        aujourd_hui = date(2026, 4, 23)
        plan = calendrier.planifier(naissance, recus, aujourd_hui=aujourd_hui)
        par_cle = {item["cle"]: item for item in plan}

        self.assertEqual(par_cle["penta_2"]["date_prevue"], date(2026, 4, 23))
        self.assertEqual(par_cle["penta_2"]["statut"], "Aujourd'hui")
        self.assertEqual(par_cle["penta_3"]["date_prevue"], date(2026, 5, 21))
        self.assertEqual(par_cle["penta_3"]["statut"], "À venir")

    def test_priorite_retard_dans_prochain_rdv(self):
        naissance = date(2026, 1, 1)
        aujourd_hui = date(2026, 2, 12)
        plan = calendrier.planifier(
            naissance,
            {"bcg": date(2026, 1, 1)},
            aujourd_hui=aujourd_hui,
        )
        rdv = calendrier.prochain_rdv(plan)
        self.assertIsNotNone(rdv)
        self.assertEqual(rdv["cle"], "vpo_0")
        self.assertEqual(rdv["statut"], "En retard")
        self.assertEqual(rdv["retard_jours"], 42)

        plan_a_jour = calendrier.planifier(
            naissance,
            {"bcg": date(2026, 1, 1), "vpo_0": date(2026, 1, 1)},
            aujourd_hui=aujourd_hui,
        )
        rdv2 = calendrier.prochain_rdv(plan_a_jour)
        self.assertEqual(rdv2["cle"], "penta_1")
        self.assertEqual(rdv2["statut"], "Aujourd'hui")

    def test_resume_couverture(self):
        naissance = date(2026, 1, 1)
        aujourd_hui = date(2026, 2, 12)
        resume = calendrier.resume_couverture(
            naissance,
            {"bcg": date(2026, 1, 1), "vpo_0": date(2026, 1, 1)},
            aujourd_hui=aujourd_hui,
        )
        self.assertEqual(resume["total"], 26)
        self.assertEqual(resume["recus"], 2)
        self.assertEqual(resume["maternite"], 1)
        self.assertEqual(resume["en_retard"], 0)
        self.assertEqual(resume["aujourd_hui"], 4)
        self.assertEqual(resume["a_venir"], 19)


class TestSnis(TestCase):
    """Tests de production locale des rapports DHIS2 (snis.py)."""

    def setUp(self):
        self.centre_sans_fosa = Centre.objects.create(
            nom="Centre Rural",
            commune="Ouidah",
            zone_sanitaire="Ouidah-Kpomassè-Tori",
        )
        self.centre_avec_fosa = Centre.objects.create(
            nom="Centre Urbain",
            commune="Cotonou",
            zone_sanitaire="Cotonou I-IV",
            code_fosa="BJ-FOSA-0123",
        )

    def test_codes_element_et_unite(self):
        self.assertEqual(snis.code_element("bcg"), "PEV_BCG")
        self.assertEqual(snis.code_element("hepb_0"), "PEV_HEPB_0")
        self.assertEqual(snis.code_element("vit_a_1"), "PEV_VIT_A_1")
        self.assertEqual(
            snis.code_unite(self.centre_sans_fosa),
            f"BJ-FOSA-PROVISOIRE-{self.centre_sans_fosa.pk}",
        )
        self.assertEqual(snis.code_unite(self.centre_avec_fosa), "BJ-FOSA-0123")

    def test_tranches_age_a_la_date_administration(self):
        naissance = date(2025, 11, 9)
        self.assertEqual(
            snis.tranche_age(naissance, date(2026, 11, 8)),
            snis.AGE_MOINS_1_AN,
        )
        self.assertEqual(
            snis.tranche_age(naissance, date(2026, 11, 9)),
            snis.AGE_1_AN_ET_PLUS,
        )

    def test_agreger_par_antigene_et_tranche(self):
        jour = date(2026, 11, 9)
        autre_jour = date(2026, 11, 8)
        User = get_user_model()
        user = User.objects.create_user("agent_snis_1", password="secret")

        nourrisson = Enfant.objects.create(
            centre=self.centre_avec_fosa,
            numero="N-01",
            nom="Dossou",
            prenom="Koffi",
            sexe="M",
            date_naissance=date(2026, 9, 1),
            nom_mere="Dossou Rosine",
        )
        bambin = Enfant.objects.create(
            centre=self.centre_avec_fosa,
            numero="N-02",
            nom="Agossou",
            prenom="Sènan",
            sexe="F",
            date_naissance=date(2025, 5, 1),
            nom_mere="Agossou Chantal",
        )

        Dose.objects.create(enfant=nourrisson, cle="penta_1", date_administration=jour, agent=user)
        Dose.objects.create(enfant=bambin, cle="penta_1", date_administration=jour, agent=user)
        Dose.objects.create(enfant=bambin, cle="var_2", date_administration=jour, agent=user)
        Dose.objects.create(enfant=nourrisson, cle="bcg", date_administration=autre_jour, agent=user)

        doses = Dose.objects.filter(enfant__centre=self.centre_avec_fosa).select_related("enfant")
        lignes = snis.agreger(doses, jour)
        self.assertEqual(len(lignes), 2)
        self.assertEqual(lignes[0]["cle"], "penta_1")
        self.assertEqual(lignes[0]["moins_1_an"], 1)
        self.assertEqual(lignes[0]["un_an_et_plus"], 1)
        self.assertEqual(lignes[0]["total"], 2)
        self.assertEqual(lignes[1]["cle"], "var_2")
        self.assertEqual(lignes[1]["moins_1_an"], 0)
        self.assertEqual(lignes[1]["un_an_et_plus"], 1)

    def test_structure_document_dhis2(self):
        jour = date(2026, 11, 9)
        User = get_user_model()
        user = User.objects.create_user("agent_snis_2", password="secret")
        lignes = [
            {
                "cle": "penta_1",
                "nom": "Pentavalent 1",
                "code_element": "PEV_PENTA_1",
                "moins_1_an": 2,
                "un_an_et_plus": 1,
                "total": 3,
            }
        ]
        doc = snis.payload(self.centre_avec_fosa, lignes, jour, user)
        self.assertEqual(snis.JEU_DE_DONNEES, "PEV_SEANCE_VACCINATION")
        self.assertEqual(snis.CORRESPONDANCE_UID, {})
        self.assertEqual(doc["dataSet"], "PEV_SEANCE_VACCINATION")
        self.assertEqual(doc["period"], "20261109")
        self.assertEqual(doc["orgUnit"], "BJ-FOSA-0123")
        self.assertEqual(doc["dataElementIdScheme"], "CODE")
        self.assertEqual(doc["orgUnitIdScheme"], "CODE")
        self.assertEqual(len(doc["dataValues"]), 2)
        elements = {
            (dv["dataElement"], dv["categoryOptionCombo"]): dv["value"]
            for dv in doc["dataValues"]
        }
        self.assertEqual(elements[("PEV_PENTA_1", snis.AGE_MOINS_1_AN)], "2")
        self.assertEqual(elements[("PEV_PENTA_1", snis.AGE_1_AN_ET_PLUS)], "1")

    def test_absence_import_reseau_dans_application(self):
        modules_interdits = {
            "urllib",
            "urllib3",
            "requests",
            "httpx",
            "http",
            "socket",
            "ftplib",
        }
        dossier_registre = Path(__file__).resolve().parent
        for fichier in dossier_registre.rglob("*.py"):
            if fichier.name == "tests.py":
                continue
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    for alias in noeud.names:
                        racine = alias.name.split(".")[0]
                        self.assertNotIn(racine, modules_interdits, msg=f"{fichier}: {alias.name}")
                elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                    racine = noeud.module.split(".")[0]
                    self.assertNotIn(racine, modules_interdits, msg=f"{fichier}: {noeud.module}")


class TestVuesEtFormulaires(TestCase):
    """Tests d'intégration des vues, formulaires, exports et cloisonnement."""

    def setUp(self):
        User = get_user_model()
        self.centre_a = Centre.objects.create(
            nom="Centre Alpha",
            commune="Abomey-Calavi",
            zone_sanitaire="Abomey-Calavi-Sô-Ava",
            code_fosa="FOSA-A",
        )
        self.centre_b = Centre.objects.create(
            nom="Centre Bêta",
            commune="Porto-Novo",
            zone_sanitaire="Porto-Novo-Aguégués-Sèmè",
            code_fosa="FOSA-B",
        )
        self.user_a = User.objects.create_user("agent_a", password="motdepasse_a")
        self.agent_a = Agent.objects.create(utilisateur=self.user_a, centre=self.centre_a)

        self.user_b = User.objects.create_user("agent_b", password="motdepasse_b")
        self.agent_b = Agent.objects.create(utilisateur=self.user_b, centre=self.centre_b)

        self.user_sans_centre = User.objects.create_user("agent_libre", password="motdepasse_l")
        self.agent_sans_centre = Agent.objects.create(utilisateur=self.user_sans_centre, centre=None)

        self.user_sans_profil = User.objects.create_user("user_nu", password="motdepasse_n")

        self.enfant_a1 = Enfant.objects.create(
            centre=self.centre_a,
            numero="A-001",
            nom="Tossou",
            prenom="Adjoua",
            sexe="F",
            date_naissance=date.today() - timedelta(days=90),
            nom_mere="Kpadonou Solange",
            cree_par=self.user_a,
        )
        self.enfant_a2 = Enfant.objects.create(
            centre=self.centre_a,
            numero="A-002",
            nom="Boko",
            prenom="Koffi",
            sexe="M",
            date_naissance=date.today() - timedelta(days=400),
            nom_mere="Hounsou Clarisse",
            cree_par=self.user_a,
        )
        self.enfant_b1 = Enfant.objects.create(
            centre=self.centre_b,
            numero="B-001",
            nom="Zinsou",
            prenom="Mawuli",
            sexe="M",
            date_naissance=date.today() - timedelta(days=120),
            nom_mere="Gbaguidi Nadine",
            cree_par=self.user_b,
        )

    def test_acces_refuse_sans_connexion(self):
        client = Client()
        urls_protegees = [
            reverse("registre:accueil"),
            reverse("registre:nouvel_enfant"),
            reverse("registre:enfant", args=[self.enfant_a1.pk]),
            reverse("registre:rendez_vous", args=[self.enfant_a1.pk]),
            reverse("registre:seance"),
            reverse("registre:seance_dhis2_json"),
            reverse("registre:seance_dhis2_csv"),
            reverse("registre:deconnexion"),
        ]
        for url in urls_protegees:
            reponse = client.get(url)
            self.assertEqual(reponse.status_code, 302, msg=f"Route {url} non protégée")
            self.assertIn("/connexion/", reponse["Location"])

        reponse_connexion = client.get(reverse("registre:connexion"))
        self.assertEqual(reponse_connexion.status_code, 200)

    def test_connexion_et_deconnexion(self):
        client = Client()
        reponse = client.post(
            reverse("registre:connexion"),
            {"username": "agent_a", "password": "motdepasse_a"},
        )
        self.assertRedirects(reponse, reverse("registre:accueil"))

        reponse_logout = client.post(reverse("registre:deconnexion"))
        self.assertRedirects(
            reponse_logout,
            reverse("registre:connexion"),
            fetch_redirect_response=False,
        )
        self.assertEqual(client.get(reverse("registre:accueil")).status_code, 302)

    def test_recherche_par_nom_de_mere(self):
        self.client.force_login(self.user_a)
        rep = self.client.get(reverse("registre:accueil"), {"q": "Kpadonou"})
        self.assertEqual(rep.status_code, 200)
        self.assertContains(rep, "Tossou")
        self.assertNotContains(rep, "Boko")

    def test_recherche_par_nom_prenom_et_numero(self):
        self.client.force_login(self.user_a)
        self.assertContains(
            self.client.get(reverse("registre:accueil"), {"q": "A-002"}),
            "Boko",
        )
        self.assertContains(
            self.client.get(reverse("registre:accueil"), {"q": "Adjoua"}),
            "A-001",
        )
        rep_autre = self.client.get(reverse("registre:accueil"), {"q": "Zinsou"})
        self.assertEqual(len(rep_autre.context["lignes_enfants"]), 0)
        self.assertNotContains(rep_autre, "B-001")
        self.assertNotContains(rep_autre, "Mawuli")

    def test_inscription_valide(self):
        self.client.force_login(self.user_a)
        rep = self.client.post(
            reverse("registre:nouvel_enfant"),
            {
                "numero": "A-003",
                "nom": "Amoussou",
                "prenom": "Fifamè",
                "sexe": "F",
                "date_naissance": (date.today() - timedelta(days=30)).isoformat(),
                "nom_mere": "Amoussou Pascaline",
                "telephone": "",
                "quartier": "Tankpè",
            },
        )
        self.assertEqual(rep.status_code, 302)
        cree = Enfant.objects.get(centre=self.centre_a, numero="A-003")
        self.assertEqual(cree.cree_par, self.user_a)

    def test_inscription_refuse_numero_en_double_dans_meme_centre(self):
        self.client.force_login(self.user_a)
        rep = self.client.post(
            reverse("registre:nouvel_enfant"),
            {
                "numero": "A-001",
                "nom": "Autre",
                "prenom": "Enfant",
                "sexe": "M",
                "date_naissance": (date.today() - timedelta(days=20)).isoformat(),
                "nom_mere": "Mère Test",
            },
        )
        self.assertEqual(rep.status_code, 200)
        self.assertContains(rep, "déjà utilisé dans ce centre")

    def test_inscription_autorise_meme_numero_autre_centre(self):
        self.client.force_login(self.user_b)
        rep = self.client.post(
            reverse("registre:nouvel_enfant"),
            {
                "numero": "A-001",
                "nom": "Sossou",
                "prenom": "Codjo",
                "sexe": "M",
                "date_naissance": (date.today() - timedelta(days=20)).isoformat(),
                "nom_mere": "Sossou Edwige",
            },
        )
        self.assertEqual(rep.status_code, 302)
        self.assertTrue(
            Enfant.objects.filter(centre=self.centre_b, numero="A-001").exists()
        )

    def test_inscription_refuse_date_naissance_future(self):
        self.client.force_login(self.user_a)
        rep = self.client.post(
            reverse("registre:nouvel_enfant"),
            {
                "numero": "A-004",
                "nom": "Futur",
                "prenom": "Test",
                "sexe": "M",
                "date_naissance": (date.today() + timedelta(days=1)).isoformat(),
                "nom_mere": "Mère Futur",
            },
        )
        self.assertEqual(rep.status_code, 200)
        self.assertContains(rep, "postérieure à la date du jour")
        self.assertFalse(
            Enfant.objects.filter(centre=self.centre_a, numero="A-004").exists()
        )

    def test_saisie_doses_et_idempotence(self):
        self.client.force_login(self.user_a)
        url = reverse("registre:enfant", args=[self.enfant_a1.pk])
        aujourd_hui = date.today().isoformat()

        rep1 = self.client.post(
            url,
            {
                "cles": ["bcg", "vpo_0"],
                "date_administration": aujourd_hui,
                "lot": "LOT-100",
            },
        )
        self.assertEqual(rep1.status_code, 302)
        self.assertEqual(self.enfant_a1.doses.count(), 2)

        rep2 = self.client.post(
            url,
            {
                "cles": ["bcg", "vpo_0"],
                "date_administration": aujourd_hui,
                "lot": "LOT-200",
            },
        )
        self.assertEqual(rep2.status_code, 302)
        self.assertEqual(self.enfant_a1.doses.count(), 2)
        self.assertEqual(Dose.objects.get(enfant=self.enfant_a1, cle="bcg").lot, "LOT-100")

    def test_saisie_rejet_cle_inconnue(self):
        self.client.force_login(self.user_a)
        url = reverse("registre:enfant", args=[self.enfant_a1.pk])

        rep = self.client.post(
            url,
            {
                "cles": ["bcg", "vaccin_inexistant"],
                "date_administration": date.today().isoformat(),
            },
        )
        self.assertEqual(rep.status_code, 302)
        self.assertEqual(self.enfant_a1.doses.count(), 1)
        self.assertTrue(Dose.objects.filter(enfant=self.enfant_a1, cle="bcg").exists())
        self.assertFalse(
            Dose.objects.filter(enfant=self.enfant_a1, cle="vaccin_inexistant").exists()
        )

        rep_seule = self.client.post(url, {"cle": "antigene_imaginaire"})
        self.assertEqual(rep_seule.status_code, 302)
        self.assertEqual(self.enfant_a1.doses.count(), 1)

    def test_cloisonnement_entre_centres(self):
        self.client.force_login(self.user_a)
        self.assertEqual(
            self.client.get(reverse("registre:enfant", args=[self.enfant_b1.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("registre:rendez_vous", args=[self.enfant_b1.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("registre:enfant", args=[self.enfant_b1.pk]),
                {"cle": "bcg"},
            ).status_code,
            404,
        )
        self.assertEqual(self.enfant_b1.doses.count(), 0)

    def test_fiche_rendez_vous_imprimable(self):
        self.client.force_login(self.user_a)
        rep = self.client.get(reverse("registre:rendez_vous", args=[self.enfant_a1.pk]))
        self.assertEqual(rep.status_code, 200)
        self.assertContains(rep, "Fiche de rendez-vous vaccinal")
        self.assertContains(rep, self.enfant_a1.numero)

    def test_rapport_seance_autre_jour_et_jour_illisible(self):
        hier = date.today() - timedelta(days=1)
        aujourd_hui = date.today()
        Dose.objects.create(
            enfant=self.enfant_a1,
            cle="bcg",
            date_administration=hier,
            agent=self.user_a,
        )
        Dose.objects.create(
            enfant=self.enfant_a2,
            cle="var_2",
            date_administration=aujourd_hui,
            agent=self.user_a,
        )
        Dose.objects.create(
            enfant=self.enfant_b1,
            cle="penta_1",
            date_administration=hier,
            agent=self.user_b,
        )

        self.client.force_login(self.user_a)
        rep_hier = self.client.get(reverse("registre:seance"), {"jour": hier.isoformat()})
        self.assertEqual(rep_hier.status_code, 200)
        self.assertContains(rep_hier, "PEV_BCG")
        self.assertNotContains(rep_hier, "PEV_VAR_2")
        self.assertNotContains(rep_hier, "PEV_PENTA_1")

        rep_invalide = self.client.get(reverse("registre:seance"), {"jour": "pas-une-date"})
        self.assertEqual(rep_invalide.status_code, 200)
        self.assertContains(rep_invalide, "PEV_VAR_2")
        self.assertNotContains(rep_invalide, "PEV_BCG")

    def test_export_dhis2_json(self):
        jour = date.today() - timedelta(days=2)
        Dose.objects.create(
            enfant=self.enfant_a1,
            cle="penta_1",
            date_administration=jour,
            agent=self.user_a,
        )
        Dose.objects.create(
            enfant=self.enfant_a2,
            cle="var_2",
            date_administration=jour,
            agent=self.user_a,
        )

        self.client.force_login(self.user_a)
        rep_json = self.client.get(
            reverse("registre:seance_dhis2_json"),
            {"jour": jour.isoformat()},
        )
        self.assertEqual(rep_json.status_code, 200)
        self.assertEqual(rep_json["Content-Type"].split(";")[0], "application/json")
        donnees = rep_json.json()
        self.assertEqual(donnees["dataSet"], "PEV_SEANCE_VACCINATION")
        self.assertEqual(donnees["orgUnit"], "FOSA-A")
        self.assertEqual(donnees["period"], jour.strftime("%Y%m%d"))
        self.assertEqual(donnees["dataElementIdScheme"], "CODE")
        self.assertEqual(donnees["orgUnitIdScheme"], "CODE")
        self.assertEqual(len(donnees["dataValues"]), 2)

    def test_export_dhis2_csv(self):
        jour = date.today() - timedelta(days=2)
        Dose.objects.create(
            enfant=self.enfant_a1,
            cle="penta_1",
            date_administration=jour,
            agent=self.user_a,
        )
        Dose.objects.create(
            enfant=self.enfant_a2,
            cle="var_2",
            date_administration=jour,
            agent=self.user_a,
        )

        self.client.force_login(self.user_a)
        rep_csv = self.client.get(
            reverse("registre:seance_dhis2_csv"),
            {"jour": jour.isoformat()},
        )
        self.assertEqual(rep_csv.status_code, 200)
        self.assertEqual(rep_csv["Content-Type"].split(";")[0], "text/csv")
        lignes_csv = list(csv.reader(io.StringIO(rep_csv.content.decode("utf-8"))))
        self.assertEqual(
            lignes_csv[0],
            ["dataElement", "period", "orgUnit", "categoryOptionCombo", "value", "comment"],
        )
        self.assertEqual(len(lignes_csv), 3)
        codes = {ligne[0] for ligne in lignes_csv[1:]}
        self.assertEqual(codes, {"PEV_PENTA_1", "PEV_VAR_2"})

    def test_agent_sans_centre(self):
        for utilisateur in (self.user_sans_centre, self.user_sans_profil):
            self.client.force_login(utilisateur)
            for nom_url, args in [
                ("registre:accueil", []),
                ("registre:nouvel_enfant", []),
                ("registre:enfant", [self.enfant_a1.pk]),
                ("registre:rendez_vous", [self.enfant_a1.pk]),
                ("registre:seance", []),
                ("registre:seance_dhis2_json", []),
                ("registre:seance_dhis2_csv", []),
            ]:
                reponse = self.client.get(reverse(nom_url, args=args))
                self.assertEqual(
                    reponse.status_code,
                    403,
                    msg=f"{utilisateur.username} sur {nom_url}",
                )
            self.client.logout()


class TestApercuEtDemonstration(TestCase):
    """Tests de la commande jeu_demonstration et du mode aperçu."""

    def test_commande_jeu_demonstration_et_reproductibilite(self):
        call_command("jeu_demonstration")
        User = get_user_model()
        demo_user = User.objects.get(username="agent.demo")
        self.assertTrue(demo_user.check_password("demonstration2026"))
        centre_demo = demo_user.agent.centre
        self.assertIsNotNone(centre_demo)
        self.assertEqual(Enfant.objects.filter(centre=centre_demo).count(), 45)

        doses_du_jour = Dose.objects.filter(
            enfant__centre=centre_demo,
            date_administration=date.today(),
        )
        self.assertGreater(doses_du_jour.count(), 0)

        premier_lot = list(
            Enfant.objects.filter(centre=centre_demo)
            .order_by("numero")
            .values_list("numero", "nom", "prenom", "date_naissance")
        )

        call_command("jeu_demonstration", "--reinitialiser")
        second_lot = list(
            Enfant.objects.filter(centre=centre_demo)
            .order_by("numero")
            .values_list("numero", "nom", "prenom", "date_naissance")
        )
        self.assertEqual(premier_lot, second_lot)

    def test_mode_apercu_desactive_par_defaut(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APERCU", None)
            self.assertFalse(est_mode_apercu())
        rep = self.client.get(reverse("registre:connexion"))
        self.assertEqual(rep.get("X-Frame-Options"), "DENY")
        self.assertNotContains(rep, "noindex, nofollow")
        self.assertNotContains(rep, "Mode démonstration")

    def test_mode_apercu_actif_attache_agent_demo_et_bandeau(self):
        call_command("jeu_demonstration")
        client = Client(enforce_csrf_checks=True)
        middleware_apercu = [
            "django.middleware.security.SecurityMiddleware",
            "whitenoise.middleware.WhiteNoiseMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "registre.apercu.ApercuMiddleware",
        ]
        with patch.dict(os.environ, {"APERCU": "1"}):
            with override_settings(APERCU=True, MIDDLEWARE=middleware_apercu):
                rep = client.get(reverse("registre:accueil"))
                self.assertEqual(rep.status_code, 200)
                self.assertContains(rep, "Mode démonstration")
                self.assertContains(rep, "noindex, nofollow")
                self.assertIsNone(rep.get("X-Frame-Options"))

                premier_enfant = Enfant.objects.filter(
                    centre__agents__utilisateur__username="agent.demo"
                ).first()
                rep_post = client.post(
                    reverse("registre:enfant", args=[premier_enfant.pk]),
                    {"cle": "bcg", "date_administration": date.today().isoformat()},
                )
                self.assertEqual(rep_post.status_code, 302)

    def test_configuration_settings_selon_variable_apercu(self):
        import regivax.settings as regivax_settings

        try:
            with patch.dict(os.environ, {"APERCU": "1"}):
                importlib.reload(regivax_settings)
                self.assertTrue(regivax_settings.APERCU)
                self.assertEqual(regivax_settings.SESSION_COOKIE_SAMESITE, "None")
                self.assertTrue(regivax_settings.SESSION_COOKIE_SECURE)
                self.assertEqual(regivax_settings.CSRF_COOKIE_SAMESITE, "None")
                self.assertTrue(regivax_settings.CSRF_COOKIE_SECURE)
                self.assertNotIn(
                    "django.middleware.clickjacking.XFrameOptionsMiddleware",
                    regivax_settings.MIDDLEWARE,
                )
                self.assertIn(
                    "registre.apercu.ApercuMiddleware",
                    regivax_settings.MIDDLEWARE,
                )

            with patch.dict(os.environ, {"APERCU": "0"}):
                importlib.reload(regivax_settings)
                self.assertFalse(regivax_settings.APERCU)
                self.assertIn(
                    "django.middleware.clickjacking.XFrameOptionsMiddleware",
                    regivax_settings.MIDDLEWARE,
                )
                self.assertNotIn(
                    "registre.apercu.ApercuMiddleware",
                    regivax_settings.MIDDLEWARE,
                )
                self.assertEqual(regivax_settings.SESSION_COOKIE_SAMESITE, "Lax")
        finally:
            os.environ.pop("APERCU", None)
            importlib.reload(regivax_settings)

    def test_jeu_demonstration_bcg_present_si_vaccine(self):
        """Tout enfant ayant au moins une dose possède le BCG."""
        call_command("jeu_demonstration")
        User = get_user_model()
        demo_user = User.objects.get(username="agent.demo")
        centre_demo = demo_user.agent.centre
        enfants = Enfant.objects.filter(centre=centre_demo)
        for enfant in enfants:
            doses = Dose.objects.filter(enfant=enfant)
            if doses.exists():
                self.assertTrue(
                    doses.filter(cle="bcg").exists(),
                    msg=f"L'enfant {enfant.numero} possède {doses.count()} dose(s) mais pas de BCG",
                )

    def test_jeu_demonstration_coherence_chronologique_hors_doses_du_jour(self):
        """Aucun enfant ne possède une dose dont la date théorique est postérieure à une dose manquante, hors doses du jour."""
        call_command("jeu_demonstration")
        User = get_user_model()
        demo_user = User.objects.get(username="agent.demo")
        centre_demo = demo_user.agent.centre
        aujourd_hui = date.today()
        for enfant in Enfant.objects.filter(centre=centre_demo):
            doses_hors_jour = Dose.objects.filter(enfant=enfant).exclude(
                date_administration=aujourd_hui
            )
            cles_presentes = {d.cle for d in doses_hors_jour}
            entrees_eligibles = []
            for entree in calendrier.CALENDRIER_PEV:
                d_theo = calendrier.date_theorique(enfant.date_naissance, entree)
                if d_theo > aujourd_hui:
                    continue
                entrees_eligibles.append((d_theo, entree["cle"]))
            entrees_eligibles.sort(key=lambda x: (x[0], calendrier.ORDRE_PAR_CLE.get(x[1], 999)))
            for d_theo_present, cle_present in entrees_eligibles:
                if cle_present not in cles_presentes:
                    continue
                for d_theo_manq, cle_manq in entrees_eligibles:
                    if cle_manq in cles_presentes:
                        continue
                    if d_theo_manq < d_theo_present:
                        self.fail(
                            f"L'enfant {enfant.numero} possède la dose {cle_present} (théorique {d_theo_present}) "
                            f"alors que la dose {cle_manq} (théorique {d_theo_manq}) est manquante, hors doses du jour."
                        )

    def test_jeu_demonstration_doses_de_naissance_coherentes(self):
        """Dès qu'un enfant a une dose, il possède les trois doses de naissance."""
        call_command("jeu_demonstration")
        centre_demo = get_user_model().objects.get(
            username="agent.demo"
        ).agent.centre
        for enfant in Enfant.objects.filter(centre=centre_demo):
            cles = set(
                Dose.objects.filter(enfant=enfant).values_list("cle", flat=True)
            )
            if not cles:
                continue
            for cle_naissance in ("bcg", "vpo_0", "hepb_0"):
                self.assertIn(
                    cle_naissance,
                    cles,
                    msg=(
                        f"L'enfant {enfant.numero} possède des doses sans la dose "
                        f"de naissance {cle_naissance}."
                    ),
                )

    def test_jeu_demonstration_minorites_et_aucune_dose_future(self):
        """Le jeu conserve des enfants sans dose, des enfants à jour et aucune dose future."""
        call_command("jeu_demonstration")
        centre_demo = get_user_model().objects.get(
            username="agent.demo"
        ).agent.centre
        aujourd_hui = date.today()
        enfants = list(Enfant.objects.filter(centre=centre_demo))
        self.assertEqual(len(enfants), 45)

        sans_dose = 0
        a_jour = 0
        for enfant in enfants:
            doses = list(Dose.objects.filter(enfant=enfant))
            if not doses:
                sans_dose += 1
                continue
            self.assertTrue(
                all(d.date_administration <= aujourd_hui for d in doses),
                msg=f"L'enfant {enfant.numero} possède une dose future.",
            )
            if len(doses) == len(calendrier.CALENDRIER_PEV):
                a_jour += 1

        self.assertGreater(sans_dose, 0)
        self.assertLess(sans_dose, len(enfants) // 2)
        self.assertGreater(a_jour, 0)
        self.assertLess(a_jour, len(enfants) // 2)

        doses_du_jour = Dose.objects.filter(
            enfant__centre=centre_demo, date_administration=aujourd_hui
        )
        self.assertGreater(doses_du_jour.count(), 0)
        ages = [
            calendrier.age_en_mois(d.enfant.date_naissance, aujourd_hui)
            for d in doses_du_jour
        ]
        self.assertTrue(any(age < 12 for age in ages))
        self.assertTrue(any(age >= 12 for age in ages))
