import re
import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache

from trazabilidad.models import EventoAuditoria
from trazabilidad.roles import ADMIN, OPERADOR
from .conftest import PW

NUEVA = "Otra-clave-segura-456"


def _enlace():
    assert len(mail.outbox) == 1
    return re.search(r"https?://[^/]+(/password/restablecer/\S+)", mail.outbox[0].body).group(1)


@pytest.mark.django_db
def test_login_muestra_enlace_recuperar(client):
    assert "password/recuperar" in client.get("/login/").content.decode()


def test_flujo_completo_y_login_con_nueva_clave(client, usuarios):
    r = client.post("/password/recuperar/", {"email": "operador@x.cl"})
    assert r.status_code == 302 and r.url.endswith("/enviado/")
    url = _enlace()
    r = client.get(url)  # Django redirige al formulario con token en sesión
    assert r.status_code == 302
    r = client.post(r.url, {"new_password1": NUEVA, "new_password2": NUEVA})
    assert r.status_code == 302 and r.url.endswith("/password/restablecida/")
    assert client.post("/login/", {"username": "operador", "password": PW}).status_code == 200  # la anterior ya no sirve
    assert client.post("/login/", {"username": "operador", "password": NUEVA}).status_code == 302
    acciones = set(EventoAuditoria.objects.values_list("accion", flat=True))
    assert {"PASSWORD_RESET_SOLICITUD", "PASSWORD_RESET_CONFIRMACION"} <= acciones


def test_correo_inexistente_misma_respuesta_sin_correo(client, usuarios):
    r = client.post("/password/recuperar/", {"email": "nadie@x.cl"})
    assert r.status_code == 302 and r.url.endswith("/enviado/")
    assert len(mail.outbox) == 0
    assert EventoAuditoria.objects.filter(accion="PASSWORD_RESET_SOLICITUD", resultado="FALLO").exists()


def test_cuenta_inactiva_no_recibe_correo(client, usuarios):
    u = usuarios[OPERADOR]; u.is_active = False; u.save()
    client.post("/password/recuperar/", {"email": u.email})
    assert len(mail.outbox) == 0


def test_enlace_de_un_solo_uso(client, usuarios):
    client.post("/password/recuperar/", {"email": "operador@x.cl"})
    url = _enlace()
    r = client.get(url)
    client.post(r.url, {"new_password1": NUEVA, "new_password2": NUEVA})
    c2 = client.__class__()
    assert "Enlace inválido" in c2.get(url, follow=True).content.decode()


def test_token_alterado_es_invalido(client, usuarios):
    client.post("/password/recuperar/", {"email": "operador@x.cl"})
    url = _enlace().rstrip("/") + "x/"
    assert "Enlace inválido" in client.get(url, follow=True).content.decode()


def test_politica_de_clave_se_aplica(client, usuarios):
    client.post("/password/recuperar/", {"email": "operador@x.cl"})
    r = client.get(_enlace())
    r = client.post(r.url, {"new_password1": "corta1", "new_password2": "corta1"})
    assert r.status_code == 200  # se reenvía el formulario con errores, no se redirige
    assert not get_user_model().objects.get(username="operador").check_password("corta1")


def test_limite_de_solicitudes_por_hora(client, usuarios, settings):
    settings.RESET_MAX_SOLICITUDES_HORA = 2
    for _ in range(4):
        r = client.post("/password/recuperar/", {"email": "operador@x.cl"})
        assert r.status_code == 302  # la respuesta no revela el límite
    assert len(mail.outbox) == 2


def test_reset_levanta_bloqueo_por_intentos(client, usuarios):
    for _ in range(5):
        client.post("/login/", {"username": "operador", "password": "mala"})
    assert client.post("/login/", {"username": "operador", "password": PW}).status_code == 429
    cache.clear()
    client.post("/password/recuperar/", {"email": "operador@x.cl"})
    r = client.get(_enlace())
    client.post(r.url, {"new_password1": NUEVA, "new_password2": NUEVA})
    assert client.post("/login/", {"username": "operador", "password": NUEVA}).status_code == 302


def test_admin_envia_enlace_a_usuario(cliente_rol, usuarios):
    c = cliente_rol(ADMIN)
    r = c.post(f"/administracion/usuarios/{usuarios[OPERADOR].pk}/reset/")
    assert r.status_code == 302 and len(mail.outbox) == 1
    assert mail.outbox[0].to == ["operador@x.cl"]
    assert EventoAuditoria.objects.filter(accion="PASSWORD_RESET_ADMIN", resultado="EXITO").exists()


def test_operador_no_puede_forzar_reset_de_otros(cliente_rol, usuarios):
    c = cliente_rol(OPERADOR)
    assert c.post(f"/administracion/usuarios/{usuarios[ADMIN].pk}/reset/").status_code == 403
    assert len(mail.outbox) == 0
