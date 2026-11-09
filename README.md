# RegiVax

RegiVax est un registre vaccinal numérique autonome conçu pour fonctionner localement sur l'ordinateur d'un centre de santé, sans connexion internet.

## Objet administratif

RegiVax répond à un besoin administratif précis : supprimer le comptage manuel de fin de journée et la ressaisie du rapport de séance grâce à la génération locale des fichiers d'import au format DHIS2 (`dataValueSets` JSON et CSV).

Cadre et limites de l'outil :

- RegiVax ne pose aucun diagnostic médical.
- RegiVax ne remplace pas le carnet de santé conservé par la famille.
- L'application n'effectue aucun appel réseau sortant : la production des rapports s'exécute intégralement sur le poste local.
- Projet déposé au Prix national de la simplification administrative du Bénin (clôture le jeudi 12 novembre 2026).

## Références du calendrier vaccinal

Le module autonome `registre/calendrier.py` (bibliothèque standard Python uniquement) implémente les 26 entrées du calendrier de référence et les règles de planification (intervalle minimal de 4 semaines entre deux doses d'une même série, priorité aux doses en retard pour le prochain rendez-vous) :

- Sources : PEV Bénin et DNPEV-SSP pour le socle BCG, VPO, Penta, PCV-13, VAR et VAA ; rotavirus introduit en décembre 2019 ; VPI à 14 semaines ; RTS,S introduit en avril 2024 ; deuxième dose rougeole-rubéole introduite en décembre 2024 à 18 mois.

## Fonctionnalités principales

- Gestion cloisonnée par centre de santé : chaque agent authentifié accède uniquement aux enfants de son centre (réponse 404 pour tout autre centre).
- Recherche rapide dans le registre du centre par nom, prénom, numéro du registre papier ou nom de la mère.
- Inscription d'un enfant avec contrôle d'unicité du numéro dans le centre et refus d'une date de naissance future.
- Fiche vaccinale de l'enfant avec saisie idempotente des doses et rejet de toute clé inconnue du calendrier.
- Fiche de rendez-vous imprimable pour la famille.
- Rapport de fin de séance journalier (`?jour=AAAA-MM-JJ`) avec répartition par antigène et tranche d'âge à la date d'administration (moins de 1 an, 1 an et plus), et export local JSON (`dataValueSets`) et CSV pour import DHIS2.
- Identifiant d'organisation provisoire distinct (`BJ-FOSA-PROVISOIRE-<id>`) lorsque le code FOSA officiel n'est pas renseigné, et table de correspondance UID DHIS2 laissée vide par conception.

## Structure du projet

```text
manage.py
requirements.txt
render.yaml
build.sh
demarrer.sh
lancer_local.sh
README.md
INSTALLATION_LOCALE.md
regivax/
  settings.py
  urls.py
  wsgi.py
registre/
  calendrier.py
  models.py
  snis.py
  views.py
  forms.py
  admin.py
  apps.py
  urls.py
  apercu.py
  tests.py
  migrations/
  management/commands/jeu_demonstration.py
  templates/registre/
```

## Démarrage rapide en environnement de démonstration

Le mode aperçu (`APERCU=1`) sert uniquement à la démonstration publique sur un jeu de 45 enfants fictifs (`agent.demo`). En usage réel au centre de santé, consultez `INSTALLATION_LOCALE.md` et utilisez `./lancer_local.sh`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./demarrer.sh
```

## Exécution des tests

```bash
python manage.py test -v 2
```
