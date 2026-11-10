#!/usr/bin/env bash
# Evidencia de optimización (rúbrica 3.1.3.4): mide las consultas del historial con 300 000 inspecciones sintéticas,
# primero con las migraciones 0001-0002 (sin índice por fecha) y luego con 0003 (índices nuevos).
# Requiere MariaDB local y un usuario con permisos (MARIADB_ARGS, p. ej. "-uroot"); usa la base aza_perf (se recrea).
set -euo pipefail
cd "$(dirname "$0")/.."
M="mariadb ${MARIADB_ARGS:--uroot}"; DB=aza_perf
export DB_ENGINE=mysql DB_NAME=$DB DB_USER="${DB_USER:-aza}" DB_PASSWORD="${DB_PASSWORD:-aza_pass}"
PY="${PYTHON:-python}"
$M -e "DROP DATABASE IF EXISTS $DB; CREATE DATABASE $DB CHARACTER SET utf8mb4"
$PY manage.py migrate trazabilidad 0002 -v0 && $PY manage.py migrate -v0 --fake-initial 2>/dev/null || true
$PY manage.py migrate trazabilidad 0002 -v0
$PY manage.py seed_demo --password "Demo-AZA-2026-xyz" --n 10 >/dev/null
$M $DB -e "INSERT INTO trazabilidad_inspeccion (id_externo,batch_id,fecha_hora,medicion_angular,estado_original,fecha_recepcion,limite_min,limite_max)
 SELECT CONCAT('PERF-',seq), 1+(seq MOD 3), NOW(3) - INTERVAL seq*50 SECOND, ((seq*37) MOD 600)/100-3,
 CASE WHEN seq MOD 100 < 85 THEN 'APROBADO' WHEN seq MOD 100 < 97 THEN 'RECHAZADO' ELSE 'SIN_RECETA' END, NOW(3), -1.5, 1.5 FROM seq_1_to_300000; ANALYZE TABLE trazabilidad_inspeccion;" >/dev/null
D1=$($M -N $DB -e "SELECT DATE_FORMAT(NOW() - INTERVAL 30 DAY,'%Y-%m-%d')"); D2=$($M -N $DB -e "SELECT DATE_FORMAT(NOW() - INTERVAL 23 DAY,'%Y-%m-%d')")
Q1="SELECT id,id_externo,fecha_hora,estado_original FROM trazabilidad_inspeccion WHERE fecha_hora >= '$D1' AND fecha_hora < '$D2' ORDER BY fecha_hora DESC LIMIT 20"
Q2="SELECT id FROM trazabilidad_inspeccion WHERE estado_original='RECHAZADO' AND fecha_hora >= '$D1' AND fecha_hora < '$D2' ORDER BY fecha_hora DESC LIMIT 20"
Q3="SELECT COUNT(*) FROM trazabilidad_inspeccion WHERE fecha_hora >= '$D1' AND fecha_hora < '$D2'"
Q4="SELECT id FROM trazabilidad_inspeccion WHERE batch_id=2 ORDER BY fecha_hora DESC LIMIT 20"
medir() {
  echo "### $1  (filas: $($M -N $DB -e 'SELECT COUNT(*) FROM trazabilidad_inspeccion'))"
  n=0; for q in "$Q1" "$Q2" "$Q3" "$Q4"; do n=$((n+1))
    t=$($M -N $DB -e "SET profiling=1; SELECT SQL_NO_CACHE * FROM ($q) x; SHOW PROFILES" | tail -1 | awk '{print $2*1000}')
    plan=$($M -N $DB -e "EXPLAIN $q" | awk -F"\t" "{print \"tipo=\"\$4\" indice=\"\$6\" filas_estimadas=\"\$9\" extra=\"\$10}")
    printf "Q%d  %8.2f ms   %s\n" "$n" "$t" "$plan"; done
}
medir "ANTES (migraciones 0001-0002)" | tee /tmp/antes.txt
$PY manage.py migrate -v0; $M $DB -e "ANALYZE TABLE trazabilidad_inspeccion" >/dev/null
medir "DESPUÉS (migración 0003: idx_insp_fecha e idx_insp_estado_fecha)"
