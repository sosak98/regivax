"""Code de transfert imprimable entre deux centres RegiVax.

Le code encode uniquement le numéro de registre, le nom, le prénom, le sexe,
la date de naissance, le nom de la mère et les doses reçues avec leur date.
Aucune donnée de contact ni de quartier n'y figure.

Format : document JSON compact, compressé avec zlib, encodé en base32 avec un
alphabet sans caractères ambigus, préfixé par RGVX1, découpé en groupes de cinq
caractères et terminé par une somme de contrôle de cinq caractères.

Aucun appel réseau n'est effectué : le code QR est produit localement par la
bibliothèque qrcode et sa fabrique SVG.
"""

from __future__ import annotations

import io
import json
from datetime import date
import zlib

import qrcode
from qrcode.image.svg import SvgPathImage

from django.db import transaction

from .calendrier import CALENDRIER_PAR_CLE, ORDRE_PAR_CLE
from .models import Dose, Enfant

PREFIXE = "RGVX1"
# Alphabet base32 de Crockford : ni I, ni L, ni O, ni U, afin d'éviter les
# confusions avec 1, 0 et les caractères voisins lors d'une saisie manuelle.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TAILLE_GROUPE = 5
TAILLE_SOMME = 5
SEPARATEURS = " -_\t\r\n"

CHAMPS_ATTENDUS = {"v", "n", "p", "s", "d", "m", "z"}


class CodeTransfertInvalide(ValueError):
    """Erreur de lecture d'un code de transfert abîmé, tronqué ou falsifié."""


def _encoder_base32(donnees: bytes) -> str:
    """Encode des octets dans l'alphabet base32 sans caractères ambigus."""
    if not donnees:
        return ""
    bits = 0
    nb_bits = 0
    sortie: list[str] = []
    for octet in donnees:
        bits = (bits << 8) | octet
        nb_bits += 8
        while nb_bits >= 5:
            nb_bits -= 5
            sortie.append(ALPHABET[(bits >> nb_bits) & 31])
    if nb_bits:
        sortie.append(ALPHABET[(bits << (5 - nb_bits)) & 31])
    return "".join(sortie)


def _decoder_base32(texte: str) -> bytes:
    """Décode une chaîne base32, en refusant un remplissage non nul."""
    bits = 0
    nb_bits = 0
    sortie = bytearray()
    for caractere in texte:
        bits = (bits << 5) | ALPHABET.index(caractere)
        nb_bits += 5
        if nb_bits >= 8:
            nb_bits -= 8
            sortie.append((bits >> nb_bits) & 0xFF)
            bits &= (1 << nb_bits) - 1
    if nb_bits and bits != 0:
        raise CodeTransfertInvalide(
            "Le code est abîmé ou tronqué : son remplissage est invalide."
        )
    return bytes(sortie)


def _somme_controle(donnees: bytes) -> str:
    """Calcule une somme de contrôle courte de cinq caractères."""
    valeur = zlib.crc32(donnees) & ((1 << (5 * TAILLE_SOMME)) - 1)
    return "".join(
        ALPHABET[(valeur >> (5 * (TAILLE_SOMME - 1 - rang))) & 31]
        for rang in range(TAILLE_SOMME)
    )


def _document(enfant: Enfant, doses) -> dict:
    """Construit le document strictement limité aux données nécessaires."""
    doses_triees = sorted(
        doses,
        key=lambda dose: (dose.date_administration, ORDRE_PAR_CLE.get(dose.cle, 999)),
    )
    return {
        "v": enfant.numero.strip(),
        "n": enfant.nom.strip(),
        "p": enfant.prenom.strip(),
        "s": enfant.sexe,
        "d": enfant.date_naissance.isoformat(),
        "m": enfant.nom_mere.strip(),
        "z": [
            [dose.cle, dose.date_administration.isoformat()]
            for dose in doses_triees
        ],
    }


def encoder(enfant: Enfant, doses) -> str:
    """Produit le code de transfert imprimable d'un enfant et de ses doses."""
    document = _document(enfant, doses)
    clair = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    compresse = zlib.compress(clair, 9)
    corps = _encoder_base32(compresse)
    groupes = [
        corps[debut : debut + TAILLE_GROUPE]
        for debut in range(0, len(corps), TAILLE_GROUPE)
    ]
    groupes.append(_somme_controle(compresse))
    return f"{PREFIXE}-" + "-".join(groupes)


def _valider_document(document, aujourd_hui: date) -> dict:
    if not isinstance(document, dict):
        raise CodeTransfertInvalide("Le contenu du code n'est pas lisible.")
    if set(document.keys()) != CHAMPS_ATTENDUS:
        raise CodeTransfertInvalide(
            "Le contenu du code ne correspond pas au format attendu."
        )

    def _chaine(nom: str, longueur_max: int) -> str:
        valeur = document.get(nom)
        if not isinstance(valeur, str) or not valeur.strip():
            raise CodeTransfertInvalide(
                f"Le champ {nom} du code est absent ou vide."
            )
        valeur = valeur.strip()
        if len(valeur) > longueur_max:
            raise CodeTransfertInvalide(
                f"Le champ {nom} du code dépasse la longueur autorisée."
            )
        return valeur

    numero = _chaine("v", 50)
    nom = _chaine("n", 100)
    prenom = _chaine("p", 100)
    nom_mere = _chaine("m", 150)

    sexe = document.get("s")
    if sexe not in ("M", "F"):
        raise CodeTransfertInvalide("Le sexe indiqué dans le code n'est pas valide.")

    try:
        date_naissance = date.fromisoformat(str(document.get("d", "")))
    except ValueError as exc:
        raise CodeTransfertInvalide(
            "La date de naissance du code n'est pas valide."
        ) from exc
    if date_naissance > aujourd_hui:
        raise CodeTransfertInvalide(
            "La date de naissance du code est postérieure à la date du jour."
        )

    doses_brutes = document.get("z")
    if not isinstance(doses_brutes, list):
        raise CodeTransfertInvalide("La liste des doses du code n'est pas valide.")

    doses: dict[str, date] = {}
    for element in doses_brutes:
        if not isinstance(element, list) or len(element) != 2:
            raise CodeTransfertInvalide(
                "Une dose du code n'est pas au format clé et date."
            )
        cle, date_brute = element
        if not isinstance(cle, str) or cle not in CALENDRIER_PAR_CLE:
            raise CodeTransfertInvalide(
                f"La clé de dose {cle!r} du code est inconnue du calendrier."
            )
        if cle in doses:
            raise CodeTransfertInvalide(
                f"La dose {cle!r} figure plusieurs fois dans le code."
            )
        try:
            date_administration = date.fromisoformat(str(date_brute))
        except ValueError as exc:
            raise CodeTransfertInvalide(
                f"La date de la dose {cle!r} n'est pas valide."
            ) from exc
        if date_administration < date_naissance:
            raise CodeTransfertInvalide(
                f"La dose {cle!r} précède la date de naissance."
            )
        if date_administration > aujourd_hui:
            raise CodeTransfertInvalide(
                f"La dose {cle!r} est datée dans le futur."
            )
        doses[cle] = date_administration

    return {
        "numero": numero,
        "nom": nom,
        "prenom": prenom,
        "sexe": sexe,
        "date_naissance": date_naissance,
        "nom_mere": nom_mere,
        "doses": doses,
    }


def decoder(texte: str, aujourd_hui: date | None = None) -> dict:
    """Relit un code de transfert et retourne les données validées."""
    if not isinstance(texte, str) or not texte.strip():
        raise CodeTransfertInvalide("Saisissez un code de transfert.")

    brut = "".join(
        caractere for caractere in texte.upper() if caractere not in SEPARATEURS
    )
    if not brut:
        raise CodeTransfertInvalide("Saisissez un code de transfert.")
    if not brut.startswith(PREFIXE):
        raise CodeTransfertInvalide(
            "Le code doit commencer par RGVX1. Vérifiez la saisie."
        )

    corps = brut[len(PREFIXE) :]
    if len(corps) <= TAILLE_SOMME:
        raise CodeTransfertInvalide(
            "Le code est tronqué : la somme de contrôle est incomplète."
        )

    corps_donnees = corps[:-TAILLE_SOMME]
    somme = corps[-TAILLE_SOMME:]
    if not corps_donnees:
        raise CodeTransfertInvalide("Le code est tronqué : aucune donnée à lire.")

    caracteres_inconnus = sorted(
        {c for c in corps_donnees + somme if c not in ALPHABET}
    )
    if caracteres_inconnus:
        raise CodeTransfertInvalide(
            "Le code contient un caractère non reconnu : "
            + ", ".join(caracteres_inconnus)
            + "."
        )

    donnees = _decoder_base32(corps_donnees)
    if _somme_controle(donnees) != somme:
        raise CodeTransfertInvalide(
            "La somme de contrôle ne correspond pas : le code est abîmé ou "
            "tronqué. Vérifiez la saisie."
        )

    try:
        clair = zlib.decompress(donnees)
    except zlib.error as exc:
        raise CodeTransfertInvalide(
            "Le code n'a pas pu être lu : il est abîmé ou tronqué."
        ) from exc

    try:
        document = json.loads(clair.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodeTransfertInvalide(
            "Le contenu du code n'est pas lisible."
        ) from exc

    return _valider_document(
        document, aujourd_hui if aujourd_hui is not None else date.today()
    )


def qr_svg(texte: str) -> str:
    """Produit le code QR en SVG, localement et sans appel réseau."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(texte)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    tampon = io.BytesIO()
    image.save(tampon)
    return tampon.getvalue().decode("utf-8")


def trouver_enfant_existant(
    centre, nom: str, prenom: str, date_naissance: date
) -> Enfant | None:
    """Retourne l'enfant du centre portant déjà les mêmes nom, prénom et naissance."""
    return Enfant.objects.filter(
        centre=centre,
        nom__iexact=nom.strip(),
        prenom__iexact=prenom.strip(),
        date_naissance=date_naissance,
    ).first()


def proposer_numero_local(centre) -> str:
    """Propose un numéro de registre local libre pour un enfant repris."""
    prefixe = "TR-"
    numeros = Enfant.objects.filter(
        centre=centre, numero__startswith=prefixe
    ).values_list("numero", flat=True)
    plus_grand = 0
    for numero in numeros:
        suffixe = numero[len(prefixe) :]
        if suffixe.isdigit():
            plus_grand = max(plus_grand, int(suffixe))
    return f"{prefixe}{plus_grand + 1:04d}"


@transaction.atomic
def creer_enfant_depuis_code(
    centre,
    donnees: dict,
    numero_local: str,
    utilisateur,
    date_reprise: date | None = None,
) -> Enfant:
    """Crée la fiche locale et les doses reprises d'un enfant transféré."""
    enfant = Enfant.objects.create(
        centre=centre,
        numero=numero_local,
        nom=donnees["nom"],
        prenom=donnees["prenom"],
        sexe=donnees["sexe"],
        date_naissance=donnees["date_naissance"],
        nom_mere=donnees["nom_mere"],
        numero_origine=donnees["numero"],
        date_reprise=date_reprise or date.today(),
        cree_par=utilisateur,
    )
    Dose.objects.bulk_create(
        [
            Dose(
                enfant=enfant,
                cle=cle,
                date_administration=date_administration,
                agent=utilisateur,
            )
            for cle, date_administration in donnees["doses"].items()
        ]
    )
    return enfant


@transaction.atomic
def completer_doses_absentes(enfant: Enfant, donnees: dict, agent) -> int:
    """Complète une fiche existante sans créer de doublon ni écraser une dose."""
    existantes = set(enfant.doses.values_list("cle", flat=True))
    nouvelles = [
        Dose(
            enfant=enfant,
            cle=cle,
            date_administration=date_administration,
            agent=agent,
        )
        for cle, date_administration in donnees["doses"].items()
        if cle not in existantes
    ]
    if nouvelles:
        Dose.objects.bulk_create(nouvelles)
    if not enfant.numero_origine:
        enfant.numero_origine = donnees["numero"]
    if enfant.date_reprise is None:
        enfant.date_reprise = date.today()
    enfant.save(update_fields=["numero_origine", "date_reprise"])
    return len(nouvelles)
