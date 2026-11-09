"""Gestion du mode aperçu (démonstration publique dans un cadre distant)."""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model

UTILISATEUR_DEMO = "agent.demo"


def est_mode_apercu() -> bool:
    """Retourne True uniquement lorsque la variable d'environnement APERCU vaut '1'."""
    return os.environ.get("APERCU", "").strip() == "1"


def apercu_actif() -> bool:
    """Indique si le mode aperçu est actif dans l'environnement courant."""
    if "APERCU" in os.environ:
        return est_mode_apercu()
    return bool(getattr(settings, "APERCU", False))


class ApercuMiddleware:
    """Rattache chaque requête au compte agent.demo sans cookie en mode aperçu.

    Ce mode sert uniquement à la démonstration publique intégrée dans un cadre
    externe où les navigateurs bloquent les cookies tiers. Hors mode aperçu,
    cet intergiciel est absent et inactif.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if apercu_actif():
            request._dont_enforce_csrf_checks = True
            User = get_user_model()
            utilisateur_demo = User.objects.filter(username=UTILISATEUR_DEMO).first()
            if utilisateur_demo is not None:
                request.user = utilisateur_demo
                request._cached_user = utilisateur_demo
        return self.get_response(request)


def contexte_apercu(request) -> dict[str, bool]:
    """Expose l'indicateur du mode aperçu aux gabarits."""
    return {"apercu_actif": apercu_actif()}
