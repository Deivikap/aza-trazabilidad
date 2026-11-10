#!/usr/bin/env bash
# Respaldo cifrado de MariaDB y MongoDB. Ejecutar desde la carpeta del proyecto (cron diario, ver docs/DESPLIEGUE.md).
# Requiere BACKUP_PASSPHRASE en .env.prod. Conserva los últimos 14 respaldos. Copia el archivo .enc fuera de la VM (p. ej. S3).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env.prod; set +a
: "${BACKUP_PASSPHRASE:?define BACKUP_PASSPHRASE en .env.prod}"
DEST="${BACKUP_DIR:-/var/backups/aza}"; mkdir -p "$DEST"; chmod 700 "$DEST"
TS=$(date +%Y%m%d-%H%M%S); TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
C="docker compose -f docker-compose.prod.yml"
$C exec -T mariadb sh -c 'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers aza_trazabilidad' | gzip > "$TMP/mariadb.sql.gz"
$C exec -T mongo sh -c 'mongodump -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db aza_trazabilidad --archive --gzip' > "$TMP/mongo.archive.gz"
tar -C "$TMP" -cf - mariadb.sql.gz mongo.archive.gz | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$DEST/aza-$TS.tar.enc"
sha256sum "$DEST/aza-$TS.tar.enc" > "$DEST/aza-$TS.tar.enc.sha256"
ls -1t "$DEST"/aza-*.tar.enc | tail -n +15 | xargs -r rm -f
echo "Respaldo OK: $DEST/aza-$TS.tar.enc"
