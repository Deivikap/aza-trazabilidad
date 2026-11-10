"""CU04 – Recepción de resultados: validación, idempotencia, persistencia dual y alarmas."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from . import mongo
from .audit import registrar
from .models import Alarma, Batch, Inspeccion

ESTADOS = {"APROBADO", "RECHAZADO", "SIN_RECETA"}
REQUERIDOS = ("id_externo", "lote_codigo", "batch_codigo", "fecha_hora", "medicion_angular", "estado_original")


class Rechazo(Exception):
    def __init__(self, status, detalle):
        self.status, self.detalle = status, detalle


def validar(payload):
    if not isinstance(payload, dict):
        raise Rechazo(400, "El cuerpo debe ser un objeto JSON.")
    faltan = [c for c in REQUERIDOS if payload.get(c) in (None, "")]
    if faltan:
        raise Rechazo(422, f"Campos faltantes: {', '.join(faltan)}.")
    for c in ("id_externo", "lote_codigo", "batch_codigo"):
        if not isinstance(payload[c], str) or len(payload[c]) > 64:
            raise Rechazo(422, f"Campo inválido: {c}.")
    if payload["estado_original"] not in ESTADOS:
        raise Rechazo(422, "estado_original inválido.")
    try:
        ang = Decimal(str(payload["medicion_angular"]))
        if ang.is_nan() or ang.is_infinite() or abs(ang) >= 1000:
            raise InvalidOperation
        ang = ang.quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        raise Rechazo(422, "medicion_angular inválida.")
    fh = parse_datetime(str(payload["fecha_hora"]))
    if fh is None:
        raise Rechazo(422, "fecha_hora inválida (ISO 8601).")
    if timezone.is_naive(fh):
        fh = timezone.make_aware(fh)
    return ang, fh


def _alarmas(insp):
    creadas = []
    if insp.batch.receta_id is None or insp.estado_original == "SIN_RECETA":
        creadas.append(Alarma.objects.create(inspeccion=insp, tipo="SIN_RECETA"))
    n = settings.ALARMA_RECHAZOS_SEGUIDOS
    ultimas = list(Inspeccion.objects.filter(batch=insp.batch).order_by("-fecha_hora", "-id")
                   .values_list("estado_original", flat=True)[:n])
    if len(ultimas) == n and all(e == "RECHAZADO" for e in ultimas):
        if not Alarma.objects.filter(inspeccion__batch=insp.batch, tipo="RECHAZOS_SEGUIDOS", estado="ABIERTA").exists():
            creadas.append(Alarma.objects.create(inspeccion=insp, tipo="RECHAZOS_SEGUIDOS"))
    return creadas


def procesar(payload, request=None):
    """Devuelve (http_status, cuerpo). MariaDB es la fuente de verdad de la idempotencia."""
    idx = payload.get("id_externo", "") if isinstance(payload, dict) else ""
    try:
        ang, fh = validar(payload)
        try:
            batch = Batch.objects.select_related("lote", "receta").get(
                codigo=payload["batch_codigo"], lote__codigo=payload["lote_codigo"])
        except Batch.DoesNotExist:
            raise Rechazo(422, "Lote/batch inexistente o no coherente.")
        rc = payload.get("receta_codigo")
        if rc and (batch.receta is None or batch.receta.codigo != rc):
            raise Rechazo(422, "receta_codigo no coincide con la receta del batch.")
    except Rechazo as r:
        registrar(request, "INGESTA_RECHAZADA", "FALLO", "Inspeccion", idx, origen="API")
        return r.status, {"error": r.detalle}

    rec = batch.receta
    try:
        with transaction.atomic():
            insp = Inspeccion.objects.create(
                id_externo=payload["id_externo"], batch=batch, fecha_hora=fh, medicion_angular=ang,
                estado_original=payload["estado_original"],
                limite_min=rec.tol_angular_min if rec else None, limite_max=rec.tol_angular_max if rec else None)
            registrar(request, "INGESTA_OK", "EXITO", "Inspeccion", insp.pk, origen="API")
    except IntegrityError:
        # duplicado: antes de responder 409 se completa MongoDB si faltara
        try:
            if mongo.obtener(payload["id_externo"]) is None:
                mongo.upsert_payload(payload["id_externo"], payload)
        except Exception:
            registrar(request, "MONGO_FALLO", "FALLO", "Inspeccion", idx, origen="API")
        registrar(request, "INGESTA_DUPLICADA", "FALLO", "Inspeccion", idx, origen="API")
        return 409, {"error": "id_externo duplicado."}

    try:  # tras confirmar MariaDB
        mongo.upsert_payload(insp.id_externo, payload)
    except Exception:
        registrar(request, "MONGO_FALLO", "FALLO", "Inspeccion", insp.pk, origen="API")
    alarmas = _alarmas(insp)
    for a in alarmas:
        registrar(request, "ALARMA_GENERADA", "EXITO", "Alarma", a.pk, origen="API")
    return 201, {"id": insp.pk, "id_externo": insp.id_externo, "alarmas": [a.tipo for a in alarmas]}
