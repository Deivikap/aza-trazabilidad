#!/usr/bin/env bash
# Prueba de humo contra el despliegue: salud, HTTPS, cabeceras, login y API (401/422/201/409).
# Uso: bash deploy/smoke_test.sh https://aza.midominio.cl <TOKEN_API>
set -u
URL="${1:?url base}"; TOK="${2:?token de la API}"; ok=0; fail=0
chk() { if [ "$2" = "$3" ]; then echo "OK    $1 -> $2"; ok=$((ok+1)); else echo "FALLA $1 -> esperado $3, obtenido $2"; fail=$((fail+1)); fi; }
chk "GET /healthz/"        "$(curl -s -o /dev/null -w '%{http_code}' "$URL/healthz/")" 200
chk "GET /login/"          "$(curl -s -o /dev/null -w '%{http_code}' "$URL/login/")" 200
chk "HTTP redirige a HTTPS" "$(curl -s -o /dev/null -w '%{http_code}' "http://${URL#https://}/login/")" 308
chk "Cabecera HSTS"        "$(curl -sI "$URL/login/" | grep -ci '^strict-transport-security')" 1
chk "Cabecera CSP"         "$(curl -sI "$URL/login/" | grep -ci '^content-security-policy')" 1
chk "Dashboard sin sesión" "$(curl -s -o /dev/null -w '%{http_code}' "$URL/")" 302
ID="SMOKE-$(date +%s)"
body() { echo "{\"id_externo\":\"$ID\",\"lote_codigo\":\"$1\",\"batch_codigo\":\"$2\",\"fecha_hora\":\"$(date -u +%FT%TZ)\",\"medicion_angular\":0.4,\"estado_original\":\"APROBADO\"}"; }
post() { curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/api/v1/inspecciones/" -H 'Content-Type: application/json' -H "Authorization: Bearer $1" -d "$2"; }
chk "API sin token (401)"      "$(post invalido "$(body LOTE-TREF-0417 BATCH-TF-71)")" 401
chk "API lote inexistente (422)" "$(post "$TOK" "$(body NO-EXISTE NO-EXISTE)")" 422
chk "API válida (201)"         "$(post "$TOK" "$(body LOTE-TREF-0417 BATCH-TF-71)")" 201
chk "API duplicado (409)"      "$(post "$TOK" "$(body LOTE-TREF-0417 BATCH-TF-71)")" 409
echo "Resultado: $ok OK, $fail con fallas"; [ "$fail" -eq 0 ]
