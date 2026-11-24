"""Simulador de la cámara de trefilado: envía resultados a la API (CU04).
Uso:  python simulador/camara.py --url http://127.0.0.1:8000 --token <TOKEN> [--n 5] [--demo-errores]"""
import argparse
import random
import time
from datetime import datetime, timezone

import requests


def enviar(url, token, payload):
    r = requests.post(f"{url}/api/v1/inspecciones/", json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    print(r.status_code, payload.get("id_externo"), r.text[:120])
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--demo-errores", action="store_true", help="Envía además un duplicado (409), un payload incompleto (422) y un token inválido (401)")
    a = ap.parse_args()
    base = int(time.time()) % 100000
    ultimo = None
    for k in range(a.n):
        ang = round(random.gauss(0, 1.1), 3)
        ultimo = dict(id_externo=f"SIM-{base}-{k}", lote_codigo="LOTE-TREF-0417", batch_codigo="BATCH-TF-71", receta_codigo="REC-TREF-01",
                      fecha_hora=datetime.now(timezone.utc).isoformat(), medicion_angular=ang,
                      estado_original="APROBADO" if -1.5 <= ang <= 1.5 else "RECHAZADO")
        enviar(a.url, a.token, ultimo)
    if a.demo_errores and ultimo:
        print("--- duplicado (409)"); enviar(a.url, a.token, ultimo)
        print("--- incompleto (422)"); enviar(a.url, a.token, {"id_externo": "SIM-INCOMPLETO"})
        print("--- token inválido (401)"); enviar(a.url, "token-invalido", ultimo)


if __name__ == "__main__":
    main()
