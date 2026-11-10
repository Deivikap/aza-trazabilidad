"""Prueba de carga (Locust) de la plataforma AZA.

Dos tipos de usuario:
  * Camara     -> simula la cámara: POST /api/v1/inspecciones/ con id_externo único (CU04).
  * Supervisor -> inicia sesión y consulta dashboard, historial con filtros y trazabilidad (CU05, CU06, CU07).
Variables: AZA_TOKEN (token de la API), AZA_USER / AZA_PASS (credenciales del supervisor).
Uso:  locust -f loadtest/locustfile.py --headless -u 20 -r 5 -t 60s --host http://127.0.0.1:8000 --csv evidencias/locust
"""
import itertools
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, task

TOKEN = os.environ.get("AZA_TOKEN", "")
USER, PASS = os.environ.get("AZA_USER", "supervisor_demo"), os.environ.get("AZA_PASS", "")
_ids = itertools.count(int(time.time()))


class Camara(HttpUser):
    weight = 3
    wait_time = between(0.5, 1.5)

    @task
    def ingesta_valida(self):
        ang = round(random.gauss(0, 1.1), 3)
        body = dict(id_externo=f"LT-{uuid.uuid4().hex[:16]}", lote_codigo="LOTE-TREF-0417", batch_codigo="BATCH-TF-71",
                    receta_codigo="REC-TREF-01", fecha_hora=datetime.now(timezone.utc).isoformat(), medicion_angular=ang,
                    estado_original="APROBADO" if -1.5 <= ang <= 1.5 else "RECHAZADO")
        self.client.post("/api/v1/inspecciones/", json=body, headers={"Authorization": f"Bearer {TOKEN}"}, name="POST /api/v1/inspecciones/ (201)")


class Supervisor(HttpUser):
    weight = 1
    wait_time = between(1, 3)

    def on_start(self):
        r = self.client.get("/login/", name="GET /login/")
        csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
        self.client.post("/login/", {"username": USER, "password": PASS, "csrfmiddlewaretoken": csrf},
                         headers={"Referer": self.host + "/login/"}, name="POST /login/")

    @task(3)
    def dashboard(self):
        self.client.get("/", name="GET / (dashboard)")

    @task(3)
    def historial(self):
        self.client.get("/historial/?estado=RECHAZADO", name="GET /historial/ (filtro)")

    @task(2)
    def trazabilidad(self):
        self.client.get("/trazabilidad/?lote=LOTE-TREF-0417", name="GET /trazabilidad/")
