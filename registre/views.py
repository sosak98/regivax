"""Vues applicatives du registre vaccinal RegiVax."""

from datetime import date

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from . import snis
from .apercu import apercu_actif
from .calendrier import (
    AGE_LIMITE_RATTRAPAGE_MOIS,
    CALENDRIER_PAR_CLE,
    age_en_mois,
    normaliser_cle,
    planifier,
    prochain_rdv,
    resume_couverture,
)
from .forms import ConnexionForm, EnfantForm
from .models import Dose, Enfant


def _obtenir_centre_agent(user):
    """Retourne le centre rattaché à l'agent connecté, ou None."""
    agent = getattr(user, "agent", None)
    if agent is None:
        return None
    return agent.centre


def _lire_jour(request) -> date:
    """Lit le paramètre ?jour=AAAA-MM-JJ et retombe sur aujourd'hui si illisible."""
    valeur = request.GET.get("jour", "").strip()
    if not valeur:
        return date.today()
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return date.today()


def connexion(request):
    """Page de connexion au registre vaccinal."""
    if request.user.is_authenticated:
        return redirect("registre:accueil")

    formulaire = ConnexionForm(request, data=request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        login(request, formulaire.get_user())
        cible = request.POST.get("next") or request.GET.get("next") or ""
        if cible and url_has_allowed_host_and_scheme(
            cible,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(cible)
        return redirect("registre:accueil")

    return render(
        request,
        "registre/connexion.html",
        {
            "formulaire": formulaire,
            "next": request.GET.get("next", ""),
        },
    )


@login_required
def deconnexion(request):
    """Déconnexion de l'agent connecté."""
    if request.method == "POST":
        logout(request)
        if apercu_actif():
            return redirect("registre:accueil")
        return redirect("registre:connexion")
    return redirect("registre:accueil")


@login_required
def accueil(request):
    """Liste et recherche des enfants enregistrés dans le centre de l'agent."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return render(request, "registre/sans_centre.html", status=403)

    requete = request.GET.get("q", "").strip()
    enfants_qs = Enfant.objects.filter(centre=centre).prefetch_related("doses")
    if requete:
        enfants_qs = enfants_qs.filter(
            Q(nom__icontains=requete)
            | Q(prenom__icontains=requete)
            | Q(numero__icontains=requete)
            | Q(nom_mere__icontains=requete)
        )

    aujourd_hui = date.today()
    lignes_enfants = []
    for enfant_obj in enfants_qs:
        planning = planifier(
            enfant_obj.date_naissance,
            enfant_obj.doses_recues(),
            aujourd_hui=aujourd_hui,
        )
        couverture = resume_couverture(planning)
        rdv = prochain_rdv(planning)
        lignes_enfants.append(
            {
                "enfant": enfant_obj,
                "age_mois": age_en_mois(enfant_obj.date_naissance, aujourd_hui),
                "couverture": couverture,
                "prochain_rdv": rdv,
            }
        )

    return render(
        request,
        "registre/accueil.html",
        {
            "centre": centre,
            "lignes_enfants": lignes_enfants,
            "q": requete,
            "total_centre": Enfant.objects.filter(centre=centre).count(),
            "aujourd_hui": aujourd_hui,
        },
    )


@login_required
def nouvel_enfant(request):
    """Inscription d'un nouvel enfant dans le registre du centre."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return render(request, "registre/sans_centre.html", status=403)

    formulaire = EnfantForm(request.POST or None, centre=centre)
    if request.method == "POST" and formulaire.is_valid():
        enfant_obj = formulaire.save(commit=False)
        enfant_obj.centre = centre
        enfant_obj.cree_par = request.user
        enfant_obj.save()
        messages.success(
            request,
            f"L'enfant {enfant_obj.nom} {enfant_obj.prenom} "
            f"(n° {enfant_obj.numero}) a été inscrit au registre.",
        )
        return redirect("registre:enfant", pk=enfant_obj.pk)

    return render(
        request,
        "registre/nouvel_enfant.html",
        {
            "centre": centre,
            "formulaire": formulaire,
        },
    )


@login_required
def enfant(request, pk):
    """Fiche individuelle de l'enfant et saisie des doses administrées."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return render(request, "registre/sans_centre.html", status=403)

    enfant_obj = get_object_or_404(Enfant, pk=pk, centre=centre)
    aujourd_hui = date.today()

    if request.method == "POST":
        cles_brutes = list(request.POST.getlist("cles"))
        cle_unique = request.POST.get("cle")
        if cle_unique:
            cles_brutes.append(cle_unique)

        date_brute = request.POST.get("date_administration", "").strip()
        if date_brute:
            try:
                date_admin = date.fromisoformat(date_brute)
            except ValueError:
                messages.error(
                    request,
                    "La date d'administration saisie n'est pas valide.",
                )
                return redirect("registre:enfant", pk=enfant_obj.pk)
        else:
            date_admin = aujourd_hui

        if date_admin > aujourd_hui:
            messages.error(
                request,
                "La date d'administration ne peut pas être postérieure à aujourd'hui.",
            )
            return redirect("registre:enfant", pk=enfant_obj.pk)

        if date_admin < enfant_obj.date_naissance:
            messages.error(
                request,
                "La date d'administration ne peut pas précéder la date de naissance.",
            )
            return redirect("registre:enfant", pk=enfant_obj.pk)

        lot_global = request.POST.get("lot", "").strip()
        ajoutees = 0
        deja_presentes = 0
        ignorees = 0
        cles_vues = set()

        for cle_brute in cles_brutes:
            cle_norm = normaliser_cle(cle_brute)
            if cle_norm not in CALENDRIER_PAR_CLE:
                ignorees += 1
                continue
            if cle_norm in cles_vues:
                continue
            cles_vues.add(cle_norm)

            lot_dose = (
                request.POST.get(f"lot_{cle_norm}", "").strip() or lot_global
            )
            _, cree = Dose.objects.get_or_create(
                enfant=enfant_obj,
                cle=cle_norm,
                defaults={
                    "date_administration": date_admin,
                    "lot": lot_dose,
                    "agent": request.user,
                },
            )
            if cree:
                ajoutees += 1
            else:
                deja_presentes += 1

        if ajoutees:
            messages.success(
                request,
                f"{ajoutees} dose(s) enregistrée(s) à la date du {date_admin:%d/%m/%Y}.",
            )
        if deja_presentes:
            messages.info(
                request,
                f"{deja_presentes} dose(s) déjà enregistrée(s) précédemment n'ont pas été dupliquées.",
            )
        if ignorees:
            messages.warning(
                request,
                f"{ignorees} clé(s) inconnue(s) du calendrier ont été ignorée(s).",
            )
        if not cles_brutes:
            messages.info(request, "Aucune dose sélectionnée pour l'enregistrement.")

        return redirect("registre:enfant", pk=enfant_obj.pk)

    doses_enregistrees = {
        dose.cle: dose for dose in enfant_obj.doses.select_related("agent")
    }
    recus_dates = {cle: dose.date_administration for cle, dose in doses_enregistrees.items()}
    planning = planifier(enfant_obj.date_naissance, recus_dates, aujourd_hui=aujourd_hui)

    for item in planning:
        dose_obj = doses_enregistrees.get(item["cle"])
        entree_cal = CALENDRIER_PAR_CLE[item["cle"]]
        item["lot"] = dose_obj.lot if dose_obj else ""
        item["categorie"] = entree_cal.get("categorie", "vaccin")

    age_mois = age_en_mois(enfant_obj.date_naissance, aujourd_hui)
    return render(
        request,
        "registre/enfant.html",
        {
            "centre": centre,
            "enfant": enfant_obj,
            "planning": planning,
            "couverture": resume_couverture(planning),
            "prochain_rdv": prochain_rdv(planning),
            "age_mois": age_mois,
            "depasse_rattrapage": age_mois > AGE_LIMITE_RATTRAPAGE_MOIS,
            "age_limite_rattrapage_mois": AGE_LIMITE_RATTRAPAGE_MOIS,
            "aujourd_hui": aujourd_hui,
        },
    )


@login_required
def rendez_vous(request, pk):
    """Fiche imprimable des prochains rendez-vous pour la famille."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return render(request, "registre/sans_centre.html", status=403)

    enfant_obj = get_object_or_404(Enfant, pk=pk, centre=centre)
    aujourd_hui = date.today()
    planning = planifier(
        enfant_obj.date_naissance,
        enfant_obj.doses_recues(),
        aujourd_hui=aujourd_hui,
    )
    prochain = prochain_rdv(planning)
    doses_prochain_jour = []
    if prochain is not None:
        doses_prochain_jour = [
            item
            for item in planning
            if item["date_prevue"] == prochain["date_prevue"]
            and item["statut"] not in ("Reçu", "À la maternité")
        ]

    doses_restantes = [
        item
        for item in planning
        if item["statut"] not in ("Reçu", "À la maternité")
    ]

    return render(
        request,
        "registre/rendez_vous.html",
        {
            "centre": centre,
            "enfant": enfant_obj,
            "age_mois": age_en_mois(enfant_obj.date_naissance, aujourd_hui),
            "couverture": resume_couverture(planning),
            "prochain_rdv": prochain,
            "doses_prochain_jour": doses_prochain_jour,
            "doses_restantes": doses_restantes,
            "aujourd_hui": aujourd_hui,
        },
    )


@login_required
def seance(request):
    """Rapport de fin de séance journalier avec synthèse DHIS2."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return render(request, "registre/sans_centre.html", status=403)

    jour = _lire_jour(request)
    doses = (
        Dose.objects.filter(
            enfant__centre=centre,
            date_administration=jour,
        )
        .select_related("enfant", "agent")
        .order_by("date_saisie", "enfant__numero", "cle")
    )
    lignes = snis.agreger(doses, jour)
    code_unite = snis.code_unite(centre)

    return render(
        request,
        "registre/seance.html",
        {
            "centre": centre,
            "jour": jour,
            "lignes": lignes,
            "doses": doses,
            "total_moins_1_an": sum(l["moins_1_an"] for l in lignes),
            "total_1_an_et_plus": sum(l["un_an_et_plus"] for l in lignes),
            "total_doses": sum(l["total"] for l in lignes),
            "jeu_de_donnees": snis.JEU_DE_DONNEES,
            "periode": jour.strftime("%Y%m%d"),
            "code_unite": code_unite,
            "code_fosa_provisoire": not bool((centre.code_fosa or "").strip()),
        },
    )


@login_required
def seance_dhis2_json(request):
    """Export JSON de la séance au format DHIS2 dataValueSets."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return JsonResponse(
            {"erreur": "Aucun centre de santé n'est rattaché à votre compte."},
            status=403,
        )

    jour = _lire_jour(request)
    doses = Dose.objects.filter(
        enfant__centre=centre,
        date_administration=jour,
    ).select_related("enfant")
    lignes = snis.agreger(doses, jour)
    doc = snis.payload(centre, lignes, jour, request.user)
    reponse = JsonResponse(
        doc,
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )
    reponse["Content-Disposition"] = (
        f'attachment; filename="regivax_dhis2_{jour:%Y%m%d}.json"'
    )
    return reponse


@login_required
def seance_dhis2_csv(request):
    """Export CSV de la séance pour import DHIS2."""
    centre = _obtenir_centre_agent(request.user)
    if centre is None:
        return HttpResponse(
            "Aucun centre de santé n'est rattaché à votre compte.",
            status=403,
            content_type="text/plain; charset=utf-8",
        )

    jour = _lire_jour(request)
    doses = Dose.objects.filter(
        enfant__centre=centre,
        date_administration=jour,
    ).select_related("enfant")
    lignes = snis.agreger(doses, jour)
    contenu = snis.generer_csv(centre, lignes, jour, request.user)
    reponse = HttpResponse(contenu, content_type="text/csv; charset=utf-8")
    reponse["Content-Disposition"] = (
        f'attachment; filename="regivax_dhis2_{jour:%Y%m%d}.csv"'
    )
    return reponse
