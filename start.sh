#!/usr/bin/env bash
# Runs the website and the Telegram bot in one service.
# If either process exits, the script exits so the host restarts the whole service.
set -euo pipefail

# A freshly created database can take a few minutes to accept connections.
for attempt in $(seq 1 30); do
  if python manage.py migrate --noinput; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Database is still unavailable, giving up." >&2
    exit 1
  fi
  echo "Database not ready (attempt $attempt/30), retrying in 10s..." >&2
  sleep 10
done
if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py ensure_admin
fi

python manage.py runbot &
gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 &

wait -n
exit 1
