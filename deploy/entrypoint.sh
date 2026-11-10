#!/bin/sh
# Espera a la base de datos, aplica migraciones y prepara estáticos antes de iniciar la aplicación.
set -e
if [ "${DB_ENGINE:-sqlite}" = "mysql" ]; then
  echo "Esperando a MariaDB en ${DB_HOST}:${DB_PORT:-3306}..."
  for i in $(seq 1 60); do nc -z "${DB_HOST}" "${DB_PORT:-3306}" && break; sleep 2; done
fi
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py collectstatic --noinput
exec "$@"
