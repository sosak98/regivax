#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

if python manage.py shell -c "import sys; from registre.models import Enfant; sys.exit(0 if Enfant.objects.exists() else 1)"; then
    echo "Base de données déjà peuplée : chargement du jeu de démonstration ignoré."
else
    python manage.py jeu_demonstration
fi
