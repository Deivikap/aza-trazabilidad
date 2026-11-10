"""Pruebas por caso de uso (EV3): flujos principales, alternativos y de borde de CU02, CU03, CU05, CU06, CU07, CU09, CU10 y CU13."""
from datetime import datetime, timezone as tz
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from trazabilidad.models import Batch, EventoAuditoria, Inspeccion, Lote, Receta
from trazabilidad.roles import ADMIN, OPERADOR, SUPERVISOR
from .conftest import payload
from .test_api import post


def enviar(client, token, idx, hora_utc, est="APROBADO", ang=0.5, batch="B-1", receta="REC-1"):
    p = payload(idx=idx, est=est, ang=ang, batch=batch, receta=receta)
    p["fecha_hora"] = f"2026-10-19T{hora_utc}:00:00Z"
    assert post(client, token, p).status_code == 201


# ---- CU07 / CU07a: dashboard con métricas por turno y por receta ------------------------------------------
def test_cu07_dashboard_agrupa_por_turno_y_receta(client, datos, token, cliente_rol):
    # America/Santiago en octubre es UTC-3: 12:00Z = 09:00 (T1), 19:00Z = 16:00 (T2), 05:00Z = 02:00 (T3)
    enviar(client, token, "T1", "12", "APROBADO")
    enviar(client, token, "T2", "19", "RECHAZADO", ang=3.0)
    enviar(client, token, "T3", "05", "APROBADO")
    enviar(client, token, "S1", "12", "SIN_RECETA", batch="B-2", receta=None)
    ctx = cliente_rol(SUPERVISOR).get(reverse("dashboard")).context
    assert ctx["total"] == 4 and ctx["rechazadas"] == 1 and ctx["sin_receta"] == 1 and ctx["pct_rechazo"] == 25.0
    turnos = {t: (n, r) for t, n, r in ctx["por_turno"]}
    assert turnos == {"T1 (06–14)": (2, 0), "T2 (14–22)": (1, 1), "T3 (22–06)": (1, 0)}
    recetas = {c: (n, r) for c, n, r in ctx["por_receta"]}
    assert recetas["REC-1"] == (3, 1) and recetas["— sin receta —"] == (1, 0)


def test_cu07_dashboard_sin_datos_no_divide_por_cero(cliente_rol, datos):
    ctx = cliente_rol(OPERADOR).get(reverse("dashboard")).context
    assert ctx["total"] == 0 and ctx["pct_rechazo"] == 0 and ctx["por_turno"] == []


# ---- CU06: historial con filtros combinados y valores de borde ---------------------------------------------
def test_cu06_filtros_combinados(client, datos, token, cliente_rol):
    enviar(client, token, "H1", "12", "APROBADO")
    enviar(client, token, "H2", "13", "RECHAZADO", ang=3.0)
    enviar(client, token, "H3", "14", "SIN_RECETA", batch="B-2", receta=None)
    c = cliente_rol(OPERADOR)
    ids = lambda q: {i.id_externo for i in c.get(reverse("historial") + q).context["pagina"]}
    assert ids("?estado=RECHAZADO") == {"H2"}
    assert ids("?receta=REC-1") == {"H1", "H2"}
    assert ids("?batch=B-2") == {"H3"}
    assert ids("?lote=L-1&estado=APROBADO") == {"H1"}
    assert ids("?desde=2026-10-19&hasta=2026-10-19") == {"H1", "H2", "H3"}
    assert ids("?desde=2026-10-20") == set()
    assert ids("?estado=INEXISTENTE") == {"H1", "H2", "H3"}  # un estado fuera de lista se ignora, no se interpreta


@pytest.mark.parametrize("q", ["?desde=abc", "?hasta=31-31-2026", "?desde=2026-02-30"])
def test_cu06_fecha_invalida_no_rompe_el_historial(cliente_rol, datos, q):
    r = cliente_rol(OPERADOR).get(reverse("historial") + q)
    assert r.status_code == 200 and list(r.context["pagina"]) == []


def test_cu12_auditoria_filtra_por_fecha_y_tolera_fecha_invalida(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    hoy = timezone.localdate().isoformat()
    assert c.get(reverse("auditoria"), {"desde": hoy, "hasta": hoy}).context["pagina"].paginator.count >= 1
    assert c.get(reverse("auditoria"), {"desde": "2000-01-01", "hasta": "2000-01-02"}).context["pagina"].paginator.count == 0
    assert c.get(reverse("auditoria"), {"desde": "xx"}).status_code == 200


def test_cu06_inyeccion_sql_en_filtros_se_trata_como_texto(client, datos, token, cliente_rol):
    enviar(client, token, "I1", "12")
    r = cliente_rol(OPERADOR).get(reverse("historial"), {"lote": "' OR 1=1 --", "batch": "'; DROP TABLE trazabilidad_inspeccion;--"})
    assert r.status_code == 200 and list(r.context["pagina"]) == []
    assert Inspeccion.objects.count() == 1


# ---- CU13: exportación -------------------------------------------------------------------------------------
@pytest.mark.parametrize("q", ["?desde=abc", "?hasta=2026-02-30"])
def test_cu13_exportar_con_fecha_invalida_no_da_error_500(cliente_rol, datos, q):
    r = cliente_rol(SUPERVISOR).get(reverse("exportar_csv") + q)
    assert r.status_code in (200, 302)


def test_cu13_limite_de_filas(client, datos, token, cliente_rol, settings):
    settings.EXPORT_MAX_FILAS = 2
    for k in range(3):
        enviar(client, token, f"E{k}", "12")
    r = cliente_rol(SUPERVISOR).get(reverse("exportar_csv"))
    assert r.status_code == 302 and r["Location"] == reverse("historial")


# ---- CU05: trazabilidad ------------------------------------------------------------------------------------
def test_cu05_trazabilidad_muestra_lote_batch_receta_e_inspecciones(client, datos, token, cliente_rol):
    enviar(client, token, "TR1", "12")
    html = cliente_rol(OPERADOR).get(reverse("trazabilidad")).content.decode()
    assert "L-1" in html and "B-1" in html and "REC-1" in html


# ---- CU10: detalle e inclusión del payload original --------------------------------------------------------
def test_cu10_detalle_muestra_limites_snapshot_y_payload_original(client, datos, token, cliente_rol):
    enviar(client, token, "D1", "12")
    i = Inspeccion.objects.get(id_externo="D1")
    c = cliente_rol(SUPERVISOR)
    r = c.get(reverse("detalle", args=[i.pk]) + "?payload=1")
    assert r.status_code == 200 and r.context["payload"]["id_externo"] == "D1"
    assert c.get(reverse("detalle", args=[999999])).status_code == 404


# ---- CU03: lotes y batches ---------------------------------------------------------------------------------
def test_cu03_crear_lote_y_batch_y_rechazar_duplicado(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    assert c.post(reverse("lotes"), {"guardar_lote": "1", "l-codigo": "L-NUEVO", "l-estado": "ACTIVO"}).status_code == 302
    lote = Lote.objects.get(codigo="L-NUEVO")
    assert c.post(reverse("lotes"), {"b-codigo": "B-NUEVO", "b-lote": lote.pk, "b-receta": datos["rec"].pk, "b-estado": "EN_PROCESO"}).status_code == 302
    assert Batch.objects.filter(codigo="B-NUEVO", lote=lote).exists()
    r = c.post(reverse("lotes"), {"guardar_lote": "1", "l-codigo": "L-NUEVO", "l-estado": "ACTIVO"})
    assert r.status_code == 200 and Lote.objects.filter(codigo="L-NUEVO").count() == 1
    assert EventoAuditoria.objects.filter(accion__in=["LOTE_CREADO", "BATCH_CREADO"]).count() == 2


# ---- CU09: recetas -----------------------------------------------------------------------------------------
def test_cu09_editar_receta_no_altera_inspecciones_previas(client, datos, token, cliente_rol):
    enviar(client, token, "R1", "12")
    rec = datos["rec"]
    r = cliente_rol(ADMIN).post(reverse("receta_editar", args=[rec.pk]), {
        "codigo": "REC-1", "nombre": "R1 ajustada", "tol_angular_min": "-0.500", "tol_angular_max": "0.500", "activa": "on"})
    assert r.status_code == 302
    rec.refresh_from_db()
    assert rec.tol_angular_max == Decimal("0.500")
    i = Inspeccion.objects.get(id_externo="R1")
    assert (i.limite_min, i.limite_max) == (Decimal("-1.500"), Decimal("1.500")) and i.estado_original == "APROBADO"
    assert EventoAuditoria.objects.filter(accion="RECETA_ACTUALIZADA").exists()


def test_cu09_receta_con_codigo_duplicado_se_rechaza(cliente_rol, datos):
    r = cliente_rol(ADMIN).post(reverse("recetas"), {"codigo": "REC-1", "nombre": "otra", "tol_angular_min": "-1", "tol_angular_max": "1", "activa": "on"})
    assert r.status_code == 200 and Receta.objects.filter(codigo="REC-1").count() == 1


# ---- CU02: usuarios ----------------------------------------------------------------------------------------
def test_cu02_baja_logica_y_no_puede_desactivarse_a_si_mismo(cliente_rol, usuarios):
    c = cliente_rol(ADMIN)
    op = usuarios[OPERADOR]
    assert c.post(reverse("usuario_toggle", args=[op.pk])).status_code == 302
    op.refresh_from_db(); assert op.is_active is False
    c.post(reverse("usuario_toggle", args=[usuarios[ADMIN].pk]))
    usuarios[ADMIN].refresh_from_db(); assert usuarios[ADMIN].is_active is True
    assert get_user_model().objects.filter(pk=op.pk).exists()  # el usuario no se borra


def test_cu02_toggle_exige_post_y_rol_admin(cliente_rol, usuarios):
    assert cliente_rol(ADMIN).get(reverse("usuario_toggle", args=[usuarios[OPERADOR].pk])).status_code == 405
    assert cliente_rol(OPERADOR).post(reverse("usuario_toggle", args=[usuarios[SUPERVISOR].pk])).status_code == 403
