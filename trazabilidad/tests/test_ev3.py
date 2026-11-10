"""Pruebas de la Evaluación 3: salud, cabeceras, triggers de BD, reconciliación y errores de la API."""
import io

import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection

from trazabilidad import mongo
from trazabilidad.models import EventoAuditoria, Inspeccion
from .conftest import payload
from .test_api import post


def test_healthz_publico_y_sin_detalles(client, db):
    r = client.get("/healthz/")
    assert r.status_code == 200 and r.json()["estado"] == "ok"
    assert set(r.json()) == {"estado", "mariadb", "mongodb"}


def test_cabeceras_de_seguridad_csp(client, db):
    r = client.get("/login/")
    csp = r["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert r["X-Frame-Options"] == "DENY" and r["X-Content-Type-Options"] == "nosniff"


def test_pagina_sin_estilos_ni_scripts_en_linea(client, db):
    html = client.get("/login/").content.decode()
    assert "<style" not in html and "onclick=" not in html


def test_400_cuerpo_no_objeto(client, datos, token):
    assert post(client, token, [1, 2, 3]).status_code == 400


def test_422_valores_invalidos(client, datos, token):
    for i, cambio in enumerate((dict(est="OTRO"), dict(ang="abc"), dict(ang=5000))):
        assert post(client, token, payload(idx=f"V-{i}", **cambio)).status_code == 422
    r = post(client, token, {**payload(idx="V-9"), "fecha_hora": "ayer"})
    assert r.status_code == 422 and Inspeccion.objects.count() == 0


def test_trigger_bd_impide_update_y_delete_por_sql_directo(client, datos, token):
    post(client, token, payload())
    with pytest.raises(DatabaseError):
        with connection.cursor() as c:
            c.execute("UPDATE trazabilidad_inspeccion SET estado_original='RECHAZADO'")
    with pytest.raises(DatabaseError):
        with connection.cursor() as c:
            c.execute("DELETE FROM trazabilidad_inspeccion")
    assert Inspeccion.objects.get().estado_original == "APROBADO"


def test_trigger_bd_bitacora_solo_insercion(client, datos, token):
    post(client, token, payload())
    with pytest.raises(DatabaseError):
        with connection.cursor() as c:
            c.execute("DELETE FROM trazabilidad_eventoauditoria")
    with pytest.raises(DatabaseError):
        with connection.cursor() as c:
            c.execute("UPDATE trazabilidad_eventoauditoria SET resultado='FALLO'")
    assert EventoAuditoria.objects.exists()


def test_reconciliar_detecta_y_repara_documentos_faltantes(client, datos, token):
    post(client, token, payload())
    mongo.coleccion().delete_one({"id_externo": "X-1"})
    with pytest.raises(SystemExit):
        call_command("reconciliar_mongo", stdout=io.StringIO())
    out = io.StringIO()
    call_command("reconciliar_mongo", "--reparar", stdout=out)
    assert "reparados: 1" in out.getvalue()
    doc = mongo.obtener("X-1")
    assert doc["reconstruido_desde_mariadb"] is True and doc["estado_original"] == "APROBADO"
    call_command("reconciliar_mongo", stdout=io.StringIO())  # ya consistente: no falla


def test_reconciliar_informa_huerfanos_sin_borrarlos(client, datos, token):
    mongo.upsert_payload("HUERFANO-1", {"id_externo": "HUERFANO-1"})
    with pytest.raises(SystemExit):
        call_command("reconciliar_mongo", "--reparar", stdout=io.StringIO())
    assert mongo.obtener("HUERFANO-1") is not None


def test_falla_de_mongo_no_pierde_la_inspeccion(client, datos, token, monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("mongo caído")
    monkeypatch.setattr(mongo, "upsert_payload", roto)
    assert post(client, token, payload()).status_code == 201
    assert Inspeccion.objects.filter(id_externo="X-1").exists()
    assert EventoAuditoria.objects.filter(accion="MONGO_FALLO").exists()


def test_crear_usuario_aplica_politica_de_clave(db):
    from django.core.management import CommandError
    from django.contrib.auth import get_user_model
    from trazabilidad.roles import role_of
    with pytest.raises(CommandError):
        call_command("crear_usuario", "u1", "--rol", "ADMIN", "--password", "corta")
    call_command("crear_usuario", "u1", "--rol", "SUPERVISOR", "--password", "Clave-larga-segura-77", stdout=io.StringIO())
    assert role_of(get_user_model().objects.get(username="u1")) == "Supervisor"


@pytest.fixture
def triggers_restaurados(django_db_blocker):
    """Se instancia ANTES que la BD transaccional: al cerrar, recrea los triggers que 'quitar_triggers' retiró
    para que el vaciado (flush) posterior a una prueba transaccional no choque con la protección contra DELETE."""
    yield
    import importlib
    from django.db import connection as cx
    if cx.vendor != "mysql":
        return
    m = importlib.import_module("trazabilidad.migrations.0002_triggers_inmutabilidad")
    with django_db_blocker.unblock(), cx.cursor() as c:
        for sql in m._mysql():
            c.execute(sql)


@pytest.fixture
def quitar_triggers(transactional_db, django_db_blocker):
    yield
    from django.db import connection as cx
    if cx.vendor != "mysql":
        return
    with cx.cursor() as c:
        for t in ("trg_insp_no_update", "trg_insp_no_delete", "trg_aud_no_update", "trg_aud_no_delete"):
            c.execute(f"DROP TRIGGER IF EXISTS {t}")


def test_concurrencia_mismo_id_externo_un_solo_201(triggers_restaurados, quitar_triggers, datos, token):
    """Ocho envíos simultáneos del mismo id_externo: MariaDB (UNIQUE) deja exactamente un 201 y el resto 409."""
    import threading
    from django.db import connections
    from django.test import Client
    if connection.vendor != "mysql":
        pytest.skip("Requiere MariaDB real (conexiones concurrentes); en SQLite en memoria no aplica.")
    codigos, barrera = [], threading.Barrier(8)

    def enviar():
        try:
            barrera.wait()
            r = Client().post("/api/v1/inspecciones/", data=payload(idx="CONC-1"), content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {token}")
            codigos.append(r.status_code)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=enviar) for _ in range(8)]
    [h.start() for h in hilos]; [h.join() for h in hilos]
    assert sorted(codigos) == [201] + [409] * 7
    assert Inspeccion.objects.filter(id_externo="CONC-1").count() == 1
    assert mongo.obtener("CONC-1") is not None


def test_rnf01_sesion_expira_a_los_30_minutos_de_inactividad(cliente_rol, datos, settings):
    from datetime import timedelta
    from django.test import Client
    from django.utils import timezone
    from django.contrib.sessions.models import Session
    from django.urls import reverse
    c = cliente_rol("Operador")
    assert settings.SESSION_COOKIE_AGE == 1800 and settings.SESSION_SAVE_EVERY_REQUEST is True
    assert c.get(reverse("dashboard")).status_code == 200
    s = Session.objects.get()
    assert timedelta(minutes=29) < s.expire_date - timezone.now() <= timedelta(minutes=30)
    Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))  # simula 30 min sin actividad
    r = c.get(reverse("dashboard"))
    assert r.status_code == 302 and "/login/" in r["Location"]


def test_rnf11_errores_no_exponen_trazas_ni_rutas(client, db):
    r = client.get("/ruta-que-no-existe/")
    cuerpo = r.content.decode()
    assert r.status_code == 404 and "Traceback" not in cuerpo and "/home/" not in cuerpo and "settings.py" not in cuerpo
