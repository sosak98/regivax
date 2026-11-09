#!/usr/bin/env bash
set -o errexit

RACINE="$(cd "$(dirname "$0")" && pwd)"
cd "$RACINE"

if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    GUNICORN=".venv/bin/gunicorn"
else
    PYTHON="python3"
    GUNICORN="gunicorn"
fi

export APERCU=1
export DEBUG="${DEBUG:-False}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-*}"
export PORT="${PORT:-8000}"

"$PYTHON" manage.py migrate --no-input
"$PYTHON" manage.py collectstatic --no-input

if ! "$PYTHON" manage.py shell -c "import sys; from registre.models import Enfant; sys.exit(0 if Enfant.objects.exists() else 1)"; then
    "$PYTHON" manage.py jeu_demonstration
fi

exec "$GUNICORN" regivax.wsgi:application --bind "0.0.0.0:$PORT"
