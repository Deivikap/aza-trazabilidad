#!/usr/bin/env bash
set -euo pipefail

pip install --no-cache-dir -r requirements-render.txt
DJANGO_DEBUG=1 python manage.py collectstatic --noinput

if [ -n "${DATABASE_URL:-}" ] || [ "${DB_ENGINE:-sqlite}" != "sqlite" ]; then
  python manage.py migrate --noinput
  python manage.py createcachetable
fi
