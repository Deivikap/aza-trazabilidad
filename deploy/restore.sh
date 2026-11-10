#!/usr/bin/env bash
# Restaura un respaldo cifrado en MariaDB y MongoDB (reemplaza los datos actuales).
# Uso: bash deploy/restore.sh /var/backups/aza/aza-YYYYmmdd-HHMMSS.tar.enc
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env.prod; set +a
F="${1:?indica el archivo .tar.enc}"; : "${BACKUP_PASSPHRASE:?define BACKUP_PASSPHRASE}"
[ -f "$F.sha256" ] && sha256sum -c "$F.sha256"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$F" | tar -C "$TMP" -xf -
C="docker compose -f docker-compose.prod.yml"
read -r -p "Esto REEMPLAZA los datos actuales. Escribe RESTAURAR para continuar: " ok; [ "$ok" = "RESTAURAR" ]
$C stop web
gunzip -c "$TMP/mariadb.sql.gz" | $C exec -T mariadb sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" aza_trazabilidad'
$C exec -T mongo sh -c 'mongorestore -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --drop' < "$TMP/mongo.archive.gz"
$C start web
$C exec -T web python manage.py reconciliar_mongo || echo "Revisa las diferencias informadas (reconciliar_mongo --reparar)."
echo "Restauración completada."
