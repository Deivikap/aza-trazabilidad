import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache

from trazabilidad import mongo
from trazabilidad.models import ApiToken, Batch, Lote, Receta
from trazabilidad.roles import ADMIN, OPERADOR, SUPERVISOR, ensure_groups

PW = "Clave-de-prueba-123"


@pytest.fixture(autouse=True)
def limpio():
    mongo.reset_para_pruebas()
    cache.clear()
    yield


@pytest.fixture
def usuarios(db):
    ensure_groups()
    U = get_user_model()
    out = {}
    for rol in (ADMIN, SUPERVISOR, OPERADOR):
        u = U.objects.create_user(rol.lower(), f"{rol.lower()}@x.cl", PW)
        u.groups.add(Group.objects.get(name=rol))
        out[rol] = u
    return out


@pytest.fixture
def cliente_rol(client, usuarios):
    def _login(rol):
        r = client.post('/login/', {'username': rol.lower(), 'password': PW})
        assert r.status_code == 302
        return client
    return _login


@pytest.fixture
def datos(db):
    rec = Receta.objects.create(codigo="REC-1", nombre="R1", tol_angular_min=Decimal("-1.500"), tol_angular_max=Decimal("1.500"))
    lote = Lote.objects.create(codigo="L-1")
    b = Batch.objects.create(codigo="B-1", lote=lote, receta=rec)
    b_sin = Batch.objects.create(codigo="B-2", lote=lote, receta=None)
    return dict(rec=rec, lote=lote, batch=b, batch_sin=b_sin)


@pytest.fixture
def token(db):
    _, t = ApiToken.crear("test")
    return t


def payload(idx="X-1", batch="B-1", est="APROBADO", ang=0.5, receta="REC-1"):
    p = dict(id_externo=idx, lote_codigo="L-1", batch_codigo=batch, fecha_hora="2026-10-19T12:30:00Z",
             medicion_angular=ang, estado_original=est)
    if receta:
        p["receta_codigo"] = receta
    return p
