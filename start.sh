#!/usr/bin/env bash
# Runs the website and the Telegram bot in one service.
# If either process exits, the script exits so the host restarts the whole service.
set -euo pipefail

python manage.py migrate --noinput
if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py ensure_admin
fi

python manage.py runbot &
gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 &

wait -n
exit 1
