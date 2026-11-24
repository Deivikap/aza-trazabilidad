"""Pruebas de CRUD completo (actualizar y eliminar con ON DELETE RESTRICT), Informe de gestión y visualización MongoDB."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from trazabilidad.models import Alarma, Batch, ConfiguracionSeguridad, EventoAuditoria, Inspeccion, Lote, Observacion, Receta
from trazabilidad.roles import ADMIN, OPERADOR, SUPERVISOR, role_of
from .conftest import PW, payload
from .test_api import post

User = get_user_model()


# ---- CRUD Usuarios (actualizar + correo único) -------------------------------------------------------------
def test_crud_usuario_editar_y_evitar_correo_duplicado(cliente_rol, usuarios):
    c = cliente_rol(ADMIN)
    op = usuarios[OPERADOR]
    r = c.post(reverse("usuario_editar", args=[op.pk]), {
        "first_name": "Operador Actualizado",
        "email": "op.nuevo@aza.cl",
        "rol": SUPERVISOR,
    })
    assert r.status_code == 302
    op.refresh_from_db()
    assert op.first_name == "Operador Actualizado" and op.email == "op.nuevo@aza.cl"
    assert role_of(op) == SUPERVISOR
    assert EventoAuditoria.objects.filter(accion="USUARIO_ACTUALIZADO", resultado="EXITO").exists()

    # No permite duplicar el correo de otro usuario
    r2 = c.post(reverse("usuario_editar", args=[op.pk]), {
        "first_name": "X",
        "email": usuarios[ADMIN].email,
        "rol": OPERADOR,
    })
    assert r2.status_code == 200
    op.refresh_from_db()
    assert op.email == "op.nuevo@aza.cl"


def test_crud_usuario_admin_no_puede_quitarse_rol_admin(cliente_rol, usuarios):
    c = cliente_rol(ADMIN)
    adm = usuarios[ADMIN]
    r = c.post(reverse("usuario_editar", args=[adm.pk]), {
        "first_name": "Admin",
        "email": adm.email,
        "rol": OPERADOR,
    })
    assert r.status_code == 200
    assert role_of(User.objects.get(pk=adm.pk)) == ADMIN


def test_crud_usuario_editar_solo_admin(cliente_rol, usuarios):
    op = usuarios[OPERADOR]
    assert cliente_rol(OPERADOR).get(reverse("usuario_editar", args=[op.pk])).status_code == 403
    assert cliente_rol(SUPERVISOR).get(reverse("usuario_editar", args=[op.pk])).status_code == 403


# ---- CRUD Lotes y Batches (actualizar + eliminar + ON DELETE RESTRICT) -------------------------------------
def test_crud_lote_editar_y_eliminar_sin_hijos(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    lote = Lote.objects.create(codigo="L-TEMP", estado="ACTIVO")
    r = c.post(reverse("lote_editar", args=[lote.pk]), {"l-codigo": "L-TEMP", "l-estado": "CERRADO"})
    assert r.status_code == 302
    lote.refresh_from_db()
    assert lote.estado == "CERRADO"
    assert EventoAuditoria.objects.filter(accion="LOTE_ACTUALIZADO").exists()

    r_del = c.post(reverse("lote_eliminar", args=[lote.pk]))
    assert r_del.status_code == 302
    assert not Lote.objects.filter(pk=lote.pk).exists()
    assert EventoAuditoria.objects.filter(accion="LOTE_ELIMINADO").exists()


def test_crud_lote_con_batches_bloqueado_por_restrict(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    lote = datos["lote"]
    r = c.post(reverse("lote_eliminar", args=[lote.pk]))
    assert r.status_code == 302
    assert Lote.objects.filter(pk=lote.pk).exists()
    assert EventoAuditoria.objects.filter(accion="LOTE_ELIMINACION_BLOQUEADA", resultado="FALLO").exists()


def test_crud_batch_editar_y_eliminar_con_y_sin_inspecciones(client, cliente_rol, datos, token):
    c = cliente_rol(ADMIN)
    b_libre = Batch.objects.create(codigo="B-LIBRE", lote=datos["lote"], receta=datos["rec"], estado="EN_PROCESO")
    r = c.post(reverse("batch_editar", args=[b_libre.pk]), {
        "b-codigo": "B-LIBRE",
        "b-lote": datos["lote"].pk,
        "b-receta": datos["rec"].pk,
        "b-estado": "FIN",
    })
    assert r.status_code == 302
    b_libre.refresh_from_db()
    assert b_libre.estado == "FIN"
    assert EventoAuditoria.objects.filter(accion="BATCH_ACTUALIZADO").exists()

    assert c.post(reverse("batch_eliminar", args=[b_libre.pk])).status_code == 302
    assert not Batch.objects.filter(pk=b_libre.pk).exists()
    assert EventoAuditoria.objects.filter(accion="BATCH_ELIMINADO").exists()

    # Batch con inspección asociada no se puede eliminar
    assert post(client, token, payload(idx="DEL-B1")).status_code == 201
    b_usado = datos["batch"]
    assert c.post(reverse("batch_eliminar", args=[b_usado.pk])).status_code == 302
    assert Batch.objects.filter(pk=b_usado.pk).exists()
    assert EventoAuditoria.objects.filter(accion="BATCH_ELIMINACION_BLOQUEADA", resultado="FALLO").exists()


# ---- CRUD Recetas (eliminar + ON DELETE RESTRICT + método POST y RBAC) ------------------------------------
def test_crud_receta_eliminar_con_y_sin_batches(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    r_libre = Receta.objects.create(codigo="REC-LIBRE", nombre="Libre", tol_angular_min=Decimal("-1"), tol_angular_max=Decimal("1"))
    assert c.post(reverse("receta_eliminar", args=[r_libre.pk])).status_code == 302
    assert not Receta.objects.filter(pk=r_libre.pk).exists()
    assert EventoAuditoria.objects.filter(accion="RECETA_ELIMINADA").exists()

    # Receta usada por un batch queda protegida
    assert c.post(reverse("receta_eliminar", args=[datos["rec"].pk])).status_code == 302
    assert Receta.objects.filter(pk=datos["rec"].pk).exists()
    assert EventoAuditoria.objects.filter(accion="RECETA_ELIMINACION_BLOQUEADA", resultado="FALLO").exists()


def test_crud_eliminaciones_exigen_post_y_admin(cliente_rol, datos):
    c_adm = cliente_rol(ADMIN)
    assert c_adm.get(reverse("lote_eliminar", args=[datos["lote"].pk])).status_code == 405
    assert c_adm.get(reverse("batch_eliminar", args=[datos["batch"].pk])).status_code == 405
    assert c_adm.get(reverse("receta_eliminar", args=[datos["rec"].pk])).status_code == 405

    c_op = cliente_rol(OPERADOR)
    assert c_op.post(reverse("lote_eliminar", args=[datos["lote"].pk])).status_code == 403
    assert c_op.post(reverse("receta_eliminar", args=[datos["rec"].pk])).status_code == 403


# ---- Informe de gestión (RBAC, filtros, métricas, gráficos CSP-safe y auditoría) ---------------------------
def test_informe_gestion_permisos_y_metricas(client, cliente_rol, datos, token):
    assert post(client, token, payload(idx="IG-1", est="APROBADO", ang=0.4)).status_code == 201
    assert post(client, token, payload(idx="IG-2", est="RECHAZADO", ang=3.2)).status_code == 201
    assert post(client, token, payload(idx="IG-3", batch="B-2", est="SIN_RECETA", ang=0.1, receta=None)).status_code == 201

    # Operador no accede al informe de gestión
    assert cliente_rol(OPERADOR).get(reverse("informe_gestion")).status_code == 403

    # Supervisor y Administrador acceden y ven el informe completo
    for rol in (SUPERVISOR, ADMIN):
        r = cliente_rol(rol).get(reverse("informe_gestion"))
        assert r.status_code == 200
        html = r.content.decode()
        assert r.context["total"] == 3 and r.context["aprobadas"] == 1 and r.context["rechazadas"] == 1 and r.context["sin_receta"] == 1
        assert "ig-chart-estados" in html and "ig-chart-angulo" in html and "ig-chart-turnos" in html
        assert "<style" not in html and "onclick=" not in html

    assert EventoAuditoria.objects.filter(accion="INFORME_GESTION_CONSULTADO", resultado="EXITO").count() >= 2


def test_informe_gestion_filtros_y_fecha_invalida(client, cliente_rol, datos, token):
    assert post(client, token, payload(idx="IGF-1", est="APROBADO", ang=0.5)).status_code == 201
    assert post(client, token, payload(idx="IGF-2", batch="B-2", est="SIN_RECETA", ang=0.2, receta=None)).status_code == 201

    c = cliente_rol(SUPERVISOR)
    r_rec = c.get(reverse("informe_gestion"), {"receta": "REC-1"})
    assert r_rec.status_code == 200 and r_rec.context["total"] == 1

    r_bad = c.get(reverse("informe_gestion"), {"desde": "fecha-mala"})
    assert r_bad.status_code == 200 and r_bad.context["total"] == 0


# ---- Detalle muestra payload MongoDB en HTML y Dashboard incluye gráficos CSP-safe -------------------------
def test_detalle_renderiza_payload_mongodb_en_html(client, cliente_rol, datos, token):
    assert post(client, token, payload(idx="MONGO-UI-1")).status_code == 201
    insp = Inspeccion.objects.get(id_externo="MONGO-UI-1")
    c = cliente_rol(SUPERVISOR)

    html_sin = c.get(reverse("detalle", args=[insp.pk])).content.decode()
    assert "?payload=1" in html_sin and "<pre" not in html_sin

    html_con = c.get(reverse("detalle", args=[insp.pk]) + "?payload=1").content.decode()
    assert "<pre" in html_con and "MONGO-UI-1" in html_con and "B-1" in html_con


def test_dashboard_incluye_graficos_sin_inline(client, cliente_rol, datos, token):
    assert post(client, token, payload(idx="DASH-G1")).status_code == 201
    r = cliente_rol(SUPERVISOR).get(reverse("dashboard"))
    html = r.content.decode()
    assert r.status_code == 200
    assert "dash-chart-estados" in html and "dash-chart-angulo" in html
    assert "<style" not in html and "onclick=" not in html


# ---- Panel de rendimiento (diario, semanal, mensual) -------------------------------------------------------
def test_rendimiento_diario_semanal_mensual_y_rbac(client, cliente_rol, datos, token, usuarios):
    from django.utils import timezone
    ahora_iso = timezone.now().isoformat()
    p1 = {**payload(idx="REND-1", est="APROBADO", ang=0.4), "fecha_hora": ahora_iso}
    p2 = {**payload(idx="REND-2", batch="B-2", est="SIN_RECETA", ang=0.2, receta=None), "fecha_hora": ahora_iso}
    assert post(client, token, p1).status_code == 201
    assert post(client, token, p2).status_code == 201

    insp = Inspeccion.objects.get(id_externo="REND-1")
    Observacion.objects.create(inspeccion=insp, usuario=usuarios[OPERADOR], contenido="Revisión de turno")
    alarma = Alarma.objects.first()
    alarma.estado = "RECONOCIDA"
    alarma.usuario_rec = usuarios[SUPERVISOR]
    alarma.fecha_rec = timezone.now()
    alarma.save()

    assert cliente_rol(OPERADOR).get(reverse("rendimiento")).status_code == 403
    c_sup = cliente_rol(SUPERVISOR)
    for per in ("diario", "semanal", "mensual"):
        r = c_sup.get(reverse("rendimiento") + f"?periodo={per}")
        html = r.content.decode()
        assert r.status_code == 200 and r.context["periodo"] == per
        assert "rend-chart-ef" in html and "<style" not in html and "onclick=" not in html
        assert len(r.context["resumen_horizontes"]) == 3
        assert len(r.context["personal"]) >= 2
    assert cliente_rol(ADMIN).get(reverse("rendimiento")).status_code == 200


# ---- Política de intentos fallidos configurable por Admin --------------------------------------------------
def test_config_seguridad_admin_modifica_limite_y_aplica_a_axes(client, cliente_rol, usuarios):
    c_adm = cliente_rol(ADMIN)
    r = c_adm.post(reverse("config_seguridad"), {"max_intentos_login": 3, "minutos_bloqueo": 20})
    assert r.status_code == 302
    cfg = ConfiguracionSeguridad.actual()
    assert cfg.max_intentos_login == 3 and cfg.minutos_bloqueo == 20
    assert EventoAuditoria.objects.filter(accion="CONFIG_SEGURIDAD_ACTUALIZADA", resultado="EXITO").exists()

    c_adm.logout()
    login_html = client.get(reverse("login")).content.decode()
    assert "Tras 3 intentos fallidos" in login_html and "20 minutos" in login_html

    # Comprueba que django-axes aplica el nuevo límite de 3 intentos en caliente
    for _ in range(3):
        client.post(reverse("login"), {"username": "operador", "password": "incorrecta"})
    r_bloq = client.post(reverse("login"), {"username": "operador", "password": PW})
    assert r_bloq.status_code == 429


def test_config_seguridad_valida_rangos_y_rbac(cliente_rol, usuarios):
    c_adm = cliente_rol(ADMIN)
    c_adm.post(reverse("config_seguridad"), {"max_intentos_login": 1, "minutos_bloqueo": 2})
    cfg = ConfiguracionSeguridad.actual()
    assert cfg.max_intentos_login == 5 and cfg.minutos_bloqueo == 15  # no acepta valores inseguros
    assert EventoAuditoria.objects.filter(accion="CONFIG_SEGURIDAD_ACTUALIZADA", resultado="FALLO").exists()

    assert cliente_rol(OPERADOR).post(reverse("config_seguridad"), {"max_intentos_login": 4, "minutos_bloqueo": 10}).status_code == 403
    assert cliente_rol(SUPERVISOR).post(reverse("config_seguridad"), {"max_intentos_login": 4, "minutos_bloqueo": 10}).status_code == 403


# ---- Aprobación y rechazo de lotes por el Supervisor -------------------------------------------------------
def test_supervisor_aprueba_y_rechaza_lote_sin_alterar_inspecciones(client, cliente_rol, datos, token):
    assert post(client, token, payload(idx="LOT-REV-1", est="RECHAZADO", ang=3.1)).status_code == 201
    lote = datos["lote"]
    c_sup = cliente_rol(SUPERVISOR)
    assert c_sup.get(reverse("revision_lotes")).status_code == 200

    r1 = c_sup.post(reverse("lote_decidir", args=[lote.pk]), {"decision": "APROBADO", "comentario": "Dentro de tolerancia global"})
    assert r1.status_code == 302
    lote.refresh_from_db()
    assert lote.decision_supervisor == "APROBADO" and lote.supervisor_decision.username == "supervisor"
    assert EventoAuditoria.objects.filter(accion="LOTE_APROBADO", resultado="EXITO").exists()

    r2 = c_sup.post(reverse("lote_decidir", args=[lote.pk]), {"decision": "RECHAZADO", "comentario": "Desviación recurrente"})
    assert r2.status_code == 302
    lote.refresh_from_db()
    assert lote.decision_supervisor == "RECHAZADO"
    assert EventoAuditoria.objects.filter(accion="LOTE_RECHAZADO", resultado="EXITO").exists()

    # La clasificación original de la inspección individual sigue inmutable
    assert Inspeccion.objects.get(id_externo="LOT-REV-1").estado_original == "RECHAZADO"


def test_revision_lotes_exclusiva_de_supervisor(cliente_rol, datos):
    lote = datos["lote"]
    assert cliente_rol(ADMIN).get(reverse("revision_lotes")).status_code == 403
    assert cliente_rol(OPERADOR).get(reverse("revision_lotes")).status_code == 403
    assert cliente_rol(ADMIN).post(reverse("lote_decidir", args=[lote.pk]), {"decision": "APROBADO"}).status_code == 403
    assert cliente_rol(OPERADOR).post(reverse("lote_decidir", args=[lote.pk]), {"decision": "RECHAZADO"}).status_code == 403
    assert cliente_rol(SUPERVISOR).get(reverse("lote_decidir", args=[lote.pk])).status_code == 405

