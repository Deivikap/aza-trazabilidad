import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError

from trazabilidad import mongo
from trazabilidad.models import Alarma, EventoAuditoria, Inspeccion
from .conftest import payload

URL = "/api/v1/inspecciones/"


def post(client, token, body):
    return client.post(URL, data=body, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")


def test_201_guarda_en_mariadb_y_mongo(client, datos, token):
    r = post(client, token, payload())
    assert r.status_code == 201
    i = Inspeccion.objects.get(id_externo="X-1")
    assert i.estado_original == "APROBADO" and i.medicion_angular == Decimal("0.500")
    assert mongo.obtener("X-1")["batch_codigo"] == "B-1"
    assert EventoAuditoria.objects.filter(accion="INGESTA_OK").exists()


def test_preserva_clasificacion_sin_recalcular(client, datos, token):
    # 9.9° está fuera de tolerancia pero la cámara dijo APROBADO: se conserva el original
    post(client, token, payload(ang=9.9, est="APROBADO"))
    assert Inspeccion.objects.get(id_externo="X-1").estado_original == "APROBADO"


def test_snapshot_de_tolerancias_y_cambio_de_receta(client, datos, token):
    post(client, token, payload())
    rec = datos["rec"]; rec.tol_angular_max = Decimal("0.100"); rec.save()
    i = Inspeccion.objects.get(id_externo="X-1")
    assert (i.limite_min, i.limite_max) == (Decimal("-1.500"), Decimal("1.500"))
    assert i.estado_original == "APROBADO"


def test_422_incompleto_y_auditado(client, datos, token):
    r = post(client, token, {"id_externo": "X-9"})
    assert r.status_code == 422
    assert EventoAuditoria.objects.filter(accion="INGESTA_RECHAZADA", resultado="FALLO").exists()


def test_422_batch_inexistente_y_receta_incoherente(client, datos, token):
    assert post(client, token, payload(batch="NO-EXISTE")).status_code == 422
    assert post(client, token, payload(idx="X-2", receta="OTRA")).status_code == 422


def test_409_duplicado_sin_crear_segunda_fila(client, datos, token):
    assert post(client, token, payload()).status_code == 201
    assert post(client, token, payload()).status_code == 409
    assert Inspeccion.objects.filter(id_externo="X-1").count() == 1


def test_409_completa_mongo_si_faltaba(client, datos, token):
    post(client, token, payload())
    mongo.coleccion().delete_one({"id_externo": "X-1"})
    assert post(client, token, payload()).status_code == 409
    assert mongo.obtener("X-1") is not None


def test_401_sin_token_o_invalido(client, datos):
    assert client.post(URL, data=payload(), content_type="application/json").status_code == 401
    assert post(client, "malo", payload()).status_code == 401


def test_429_a_la_peticion_61(client, datos, token):
    codes = [post(client, token, payload(idx=f"R-{k}")).status_code for k in range(61)]
    assert codes[:60].count(201) == 60 and codes[60] == 429


def test_sin_receta_genera_alarma(client, datos, token):
    r = post(client, token, payload(idx="S-1", batch="B-2", est="SIN_RECETA", receta=None))
    assert r.status_code == 201 and "SIN_RECETA" in r.json()["alarmas"]
    assert Alarma.objects.filter(tipo="SIN_RECETA", estado="ABIERTA").count() == 1


def test_tres_rechazos_seguidos_generan_una_alarma(client, datos, token):
    for k in range(4):
        post(client, token, payload(idx=f"RZ-{k}", est="RECHAZADO", ang=3))
    assert Alarma.objects.filter(tipo="RECHAZOS_SEGUIDOS").count() == 1


def test_inmutabilidad_del_resultado(client, datos, token):
    post(client, token, payload())
    i = Inspeccion.objects.get(id_externo="X-1")
    i.estado_original = "RECHAZADO"
    with pytest.raises(ValidationError):
        i.save()
    with pytest.raises(ValidationError):
        i.delete()


def test_auditoria_append_only(client, datos, token):
    post(client, token, payload())
    e = EventoAuditoria.objects.first()
    e.accion = "X"
    with pytest.raises(ValidationError):
        e.save()
    with pytest.raises(ValidationError):
        e.delete()
