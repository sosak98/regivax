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

if [ -f ".env" ]; then
    set -a
    . ./.env
    set +a
fi

if [ -z "${SECRET_KEY:-}" ]; then
    SECRET_KEY="$("$PYTHON" -c "import secrets; print(secrets.token_urlsafe(50))")"
    printf "SECRET_KEY=%s\n" "$SECRET_KEY" >> .env
    export SECRET_KEY
fi

export APERCU=0
export DEBUG=False
export ALLOWED_HOSTS="127.0.0.1,localhost"
export PORT="${PORT:-8000}"

"$PYTHON" manage.py migrate --no-input
"$PYTHON" manage.py collectstatic --no-input

echo "RegiVax est accessible localement sur http://127.0.0.1:$PORT/"
exec "$GUNICORN" regivax.wsgi:application --bind "127.0.0.1:$PORT"
