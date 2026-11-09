#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

if [ "${APERCU:-0}" = "1" ]; then
    # En mode démonstration publique, le jeu fictif est régénéré à chaque
    # déploiement afin que la règle de cohérence du jeu soit toujours appliquée.
    python manage.py jeu_demonstration --reinitialiser
elif python manage.py shell -c "import sys; from registre.models import Enfant; sys.exit(0 if Enfant.objects.exists() else 1)"; then
    echo "Base de données déjà peuplée : chargement du jeu de démonstration ignoré."
else
    python manage.py jeu_demonstration
fi
