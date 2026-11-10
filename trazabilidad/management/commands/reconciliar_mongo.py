"""Reconcilia MariaDB (fuente de verdad) con MongoDB (payload JSON crudo) y repara fallas parciales.

Uso:  python manage.py reconciliar_mongo            # solo informa (código de salida 1 si hay diferencias)
      python manage.py reconciliar_mongo --reparar  # reconstruye en MongoDB lo que falte
Nunca borra datos: los documentos huérfanos de MongoDB solo se informan para revisión manual.
"""
from django.core.management.base import BaseCommand

from trazabilidad import mongo
from trazabilidad.audit import registrar
from trazabilidad.models import Inspeccion


class Command(BaseCommand):
    help = "Detecta y repara inspecciones sin documento en MongoDB y documentos huérfanos."

    def add_arguments(self, p):
        p.add_argument("--reparar", action="store_true", help="Reconstruye los documentos faltantes desde MariaDB.")

    def handle(self, *a, **o):
        en_mongo = mongo.ids()
        en_sql = set(Inspeccion.objects.values_list("id_externo", flat=True))
        faltan = sorted(en_sql - en_mongo)
        huerfanos = sorted(en_mongo - en_sql)
        reparados = 0
        if o["reparar"]:
            for insp in Inspeccion.objects.select_related("batch__lote", "batch__receta").filter(id_externo__in=faltan):
                doc = dict(id_externo=insp.id_externo, lote_codigo=insp.batch.lote.codigo, batch_codigo=insp.batch.codigo,
                           fecha_hora=insp.fecha_hora.isoformat(), medicion_angular=str(insp.medicion_angular),
                           estado_original=insp.estado_original, reconstruido_desde_mariadb=True)
                if insp.batch.receta:
                    doc["receta_codigo"] = insp.batch.receta.codigo
                mongo.upsert_payload(insp.id_externo, doc)
                reparados += 1
        self.stdout.write(f"MariaDB: {len(en_sql)} · MongoDB: {len(en_mongo)} · sin documento: {len(faltan)} · "
                          f"huérfanos: {len(huerfanos)} · reparados: {reparados}")
        for x in huerfanos:
            self.stdout.write(f"  HUÉRFANO (revisar manualmente): {x}")
        registrar(None, "RECONCILIACION", "EXITO" if not (faltan or huerfanos) or o["reparar"] else "FALLO",
                  "Inspeccion", f"faltan={len(faltan)};huerfanos={len(huerfanos)};reparados={reparados}", origen="SISTEMA")
        if (len(faltan) - reparados) or huerfanos:
            raise SystemExit(1)
