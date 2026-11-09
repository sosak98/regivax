# Installation locale sur le poste du centre de santé

Ce guide décrit l'installation et l'exploitation réelle de RegiVax sur l'ordinateur d'un centre de santé, en écoute locale stricte (`127.0.0.1`) et sans connexion internet requise après installation.

## Prérequis

- Python 3.11 ou supérieur.
- Droits d'exécution locale sur le poste du centre.

## 1. Préparer l'environnement Python

Dans le dossier du projet :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Pour une installation sur un poste dépourvu d'accès réseau dès le départ, téléchargez les paquets au préalable sur une machine connectée :

```bash
pip download -r requirements.txt -d paquets_hors_ligne
```

Puis installez-les hors ligne sur le poste du centre :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --no-index --find-links=paquets_hors_ligne -r requirements.txt
```

## 2. Initialiser la base locale et créer le centre

Appliquez les migrations puis créez le compte administrateur local :

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
```

## 3. Lancer l'application en usage réel

Rendez le script exécutable une fois si nécessaire :

```bash
chmod +x lancer_local.sh
./lancer_local.sh
```

Le script :

1. Charge ou génère une clé secrète locale dans `.env` (non versionnée).
2. Force le mode réel (`APERCU=0`, authentification et en-têtes de sécurité complets).
3. Applique les migrations et collecte les fichiers statiques.
4. Démarre le serveur sur `http://127.0.0.1:8000/` uniquement.

## 4. Configurer le centre de santé et les agents

1. Ouvrez `http://127.0.0.1:8000/admin/` avec le compte administrateur créé à l'étape 2.
2. Créez le centre de santé (nom, commune, zone sanitaire et code FOSA officiel s'il est disponible).
3. Créez un compte utilisateur pour chaque agent vaccinateur.
4. Créez une fiche `Agent` reliant chaque utilisateur au centre de santé.
5. Déconnectez-vous de l'administration et connectez-vous sur `http://127.0.0.1:8000/connexion/`.

## 5. Sauvegarde des données

Toutes les données du registre sont stockées localement dans le fichier `db.sqlite3`. Effectuez une copie régulière de ce fichier sur un support externe sécurisé en fin de semaine ou selon la procédure interne du centre.
