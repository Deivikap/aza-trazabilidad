#!/usr/bin/env bash
# Verifica el ciclo respaldo cifrado -> restauración de MariaDB en una base temporal y compara integridad
# (conteos, CHECKSUM TABLE y triggers). Sirve como evidencia reproducible sin Docker. Uso: bash deploy/prueba_respaldo_mariadb.sh
set -euo pipefail
SRC="${SRC_DB:-aza_trazabilidad}"; DST="${DST_DB:-aza_restore_prueba}"; PASS_BK="${BACKUP_PASSPHRASE:-frase-de-prueba-no-usar-en-produccion}"
M="mariadb ${MARIADB_ARGS:--uroot}"; TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
echo "[1] Respaldo de $SRC (single-transaction, triggers y rutinas) cifrado con AES-256-CBC + PBKDF2"
mariadb-dump ${MARIADB_ARGS:--uroot} --single-transaction --routines --triggers "$SRC" | gzip > "$TMP/mariadb.sql.gz"
tar -C "$TMP" -cf - mariadb.sql.gz | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "pass:$PASS_BK" -out "$TMP/aza.tar.enc"
sha256sum "$TMP/aza.tar.enc" | sed "s#$TMP/##"; ls -l "$TMP/aza.tar.enc" | awk '{print "tamano_bytes",$5}'
echo "[2] Verificación: el archivo cifrado NO contiene texto SQL legible"
if openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "pass:clave-incorrecta" -in "$TMP/aza.tar.enc" 2>/dev/null | tar -tf - >/dev/null 2>&1; then echo "FALLA: abrió con clave incorrecta"; exit 1; else echo "OK: con clave incorrecta no se puede abrir"; fi
echo "[3] Restauración en $DST"; T0=$(date +%s.%N)
$M -e "DROP DATABASE IF EXISTS $DST; CREATE DATABASE $DST CHARACTER SET utf8mb4"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "pass:$PASS_BK" -in "$TMP/aza.tar.enc" | tar -C "$TMP" -xf -
gunzip -c "$TMP/mariadb.sql.gz" | $M "$DST"
T1=$(date +%s.%N); printf "Tiempo de restauración (RTO medido): %.1f s\n" "$(echo "$T1 - $T0" | bc -l)"
echo "[4] Comparación de integridad origen vs restaurado"
for t in trazabilidad_inspeccion trazabilidad_eventoauditoria trazabilidad_alarma trazabilidad_batch trazabilidad_receta; do
  a=$($M -N -e "SELECT COUNT(*) FROM $SRC.$t"); b=$($M -N -e "SELECT COUNT(*) FROM $DST.$t")
  ca=$($M -N -e "CHECKSUM TABLE $SRC.$t" | awk '{print $2}'); cb=$($M -N -e "CHECKSUM TABLE $DST.$t" | awk '{print $2}')
  if [ "$a" = "$b" ] && [ "$ca" = "$cb" ]; then echo "OK    $t filas=$a checksum=$ca"; else echo "FALLA $t origen=$a/$ca restaurado=$b/$cb"; exit 1; fi
done
ta=$($M -N -e "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='$DST'")
echo "Triggers en la base restaurada: $ta (esperado 4)"; [ "$ta" = "4" ]
$M -e "DROP DATABASE $DST"; echo "Ciclo de respaldo y restauración verificado."
