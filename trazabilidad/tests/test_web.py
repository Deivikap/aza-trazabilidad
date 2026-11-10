import pytest
from django.urls import reverse

from trazabilidad.models import Alarma, EventoAuditoria, Inspeccion, Observacion
from trazabilidad.roles import ADMIN, OPERADOR, SUPERVISOR
from .conftest import PW, payload
from .test_api import post


def sembrar(client, token):
    post(client, token, payload("W-1"))
    return Inspeccion.objects.get(id_externo="W-1")


@pytest.mark.parametrize("rol,url,esperado", [
    (ADMIN, "usuarios", 200), (SUPERVISOR, "usuarios", 403), (OPERADOR, "usuarios", 403),
    (ADMIN, "auditoria", 200), (OPERADOR, "auditoria", 403), (SUPERVISOR, "auditoria", 403),
    (ADMIN, "recetas", 200), (OPERADOR, "recetas", 403),
    (ADMIN, "lotes", 200), (SUPERVISOR, "lotes", 403),
    (OPERADOR, "alarmas", 200), (SUPERVISOR, "alarmas", 200), (ADMIN, "alarmas", 403),
    (ADMIN, "dashboard", 200), (SUPERVISOR, "dashboard", 200), (OPERADOR, "dashboard", 200),
    (ADMIN, "historial", 200), (OPERADOR, "trazabilidad", 200),
    (SUPERVISOR, "exportar_csv", 200), (OPERADOR, "exportar_csv", 403), (ADMIN, "exportar_csv", 403),
])
def test_matriz_de_permisos(cliente_rol, datos, rol, url, esperado):
    assert cliente_rol(rol).get(reverse(url)).status_code == esperado


def test_acceso_denegado_queda_auditado(cliente_rol, datos):
    cliente_rol(OPERADOR).get(reverse("usuarios"))
    assert EventoAuditoria.objects.filter(accion="ACCESO_DENEGADO", resultado="FALLO").exists()


def test_anonimo_redirige_a_login(client, datos):
    r = client.get(reverse("historial"))
    assert r.status_code == 302 and "/login/" in r["Location"]


def test_login_ok_y_mensaje_generico(client, usuarios):
    assert client.post(reverse("login"), {"username": "operador", "password": PW}).status_code == 302
    client.logout()
    r = client.post(reverse("login"), {"username": "operador", "password": "mala"})
    assert r.status_code == 200 and "Credenciales inválidas" in r.content.decode()


def test_bloqueo_al_quinto_intento(client, usuarios):
    for _ in range(5):
        client.post(reverse("login"), {"username": "operador", "password": "mala"})
    r = client.post(reverse("login"), {"username": "operador", "password": PW})
    assert r.status_code == 429  # bloqueada aunque la contraseña sea correcta


def test_operador_registra_observacion_y_se_escapa_xss(cliente_rol, datos, token):
    c = cliente_rol(OPERADOR); i = sembrar(c, token)
    c.post(reverse("detalle", args=[i.pk]), {"contenido": "<script>alert(1)</script>"})
    assert Observacion.objects.count() == 1
    html = c.get(reverse("detalle", args=[i.pk])).content.decode()
    assert "&lt;script&gt;" in html and "<script>alert(1)" not in html


def test_admin_no_puede_registrar_observaciones(cliente_rol, datos, token):
    c = cliente_rol(ADMIN); i = sembrar(c, token)
    assert c.post(reverse("detalle", args=[i.pk]), {"contenido": "x"}).status_code == 403
    assert Observacion.objects.count() == 0


def test_observacion_mayor_a_500_se_rechaza(cliente_rol, datos, token):
    c = cliente_rol(SUPERVISOR); i = sembrar(c, token)
    c.post(reverse("detalle", args=[i.pk]), {"contenido": "a" * 501})
    assert Observacion.objects.count() == 0


def test_reconocer_alarma(cliente_rol, datos, token):
    post(cliente_rol(SUPERVISOR), token, payload("A-1", batch="B-2", est="SIN_RECETA", receta=None))
    a = Alarma.objects.get()
    cliente_rol(OPERADOR).post(reverse("reconocer", args=[a.pk]))
    a.refresh_from_db()
    assert a.estado == "RECONOCIDA" and a.usuario_rec.username == "operador"


def test_csv_neutraliza_formulas_y_audita(cliente_rol, datos, token):
    c = cliente_rol(SUPERVISOR)
    post(c, token, payload("=CMD()"))
    csv = c.get(reverse("exportar_csv")).content.decode()
    assert "'=CMD()" in csv and "\n=CMD()" not in csv
    assert EventoAuditoria.objects.filter(accion="EXPORTAR_CSV").exists()


def test_filtro_historial_por_estado(cliente_rol, datos, token):
    c = cliente_rol(OPERADOR)
    post(c, token, payload("F-1", est="RECHAZADO", ang=4)); post(c, token, payload("F-2"))
    html = c.get(reverse("historial") + "?estado=RECHAZADO").content.decode()
    assert "F-1" in html and "F-2" not in html


def test_admin_crea_usuario_con_politica_de_clave(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    base = dict(username="nuevo", first_name="N", email="n@x.cl", rol=OPERADOR)
    c.post(reverse("usuarios"), {**base, "password": "corta"})
    from django.contrib.auth import get_user_model
    assert not get_user_model().objects.filter(username="nuevo").exists()
    c.post(reverse("usuarios"), {**base, "password": "Una-clave-larga-segura-77"})
    assert get_user_model().objects.filter(username="nuevo").exists()


def test_receta_min_menor_que_max(cliente_rol, datos):
    c = cliente_rol(ADMIN)
    c.post(reverse("recetas"), dict(codigo="R-X", nombre="x", tol_angular_min="2", tol_angular_max="1", activa="on"))
    from trazabilidad.models import Receta
    assert not Receta.objects.filter(codigo="R-X").exists()
