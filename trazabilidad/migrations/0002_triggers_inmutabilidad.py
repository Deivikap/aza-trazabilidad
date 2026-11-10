"""Triggers de base de datos que blindan la inmutabilidad (RF-10, RF-23) incluso ante SQL directo.

MariaDB/MySQL usan SIGNAL; SQLite (desarrollo y pruebas) usa RAISE(ABORT).
"""
from django.db import migrations

CAMPOS = ["id_externo", "batch_id", "fecha_hora", "medicion_angular", "estado_original", "limite_min", "limite_max"]
MSG_INSP = "La clasificación y el resultado original de una inspección son inmutables."
MSG_DEL = "Las inspecciones y la bitácora no se eliminan."
MSG_AUD = "La bitácora de auditoría es de solo inserción."


def _mysql():
    cond = " OR ".join(f"NOT (OLD.{c} <=> NEW.{c})" for c in CAMPOS)
    return [
        f"CREATE TRIGGER trg_insp_no_update BEFORE UPDATE ON trazabilidad_inspeccion FOR EACH ROW BEGIN "  # nosec B608 (DDL con constantes del módulo; sin entrada de usuario)
        f"IF {cond} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_INSP}'; END IF; END",
        f"CREATE TRIGGER trg_insp_no_delete BEFORE DELETE ON trazabilidad_inspeccion FOR EACH ROW BEGIN "
        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_DEL}'; END",
        f"CREATE TRIGGER trg_aud_no_update BEFORE UPDATE ON trazabilidad_eventoauditoria FOR EACH ROW BEGIN "  # nosec B608 (DDL con constantes del módulo; sin entrada de usuario)
        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_AUD}'; END",
        f"CREATE TRIGGER trg_aud_no_delete BEFORE DELETE ON trazabilidad_eventoauditoria FOR EACH ROW BEGIN "
        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_DEL}'; END",
    ]


def _sqlite():
    cond = " OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in CAMPOS)
    return [
        f"CREATE TRIGGER trg_insp_no_update BEFORE UPDATE ON trazabilidad_inspeccion FOR EACH ROW WHEN {cond} "
        f"BEGIN SELECT RAISE(ABORT, '{MSG_INSP}'); END",
        f"CREATE TRIGGER trg_insp_no_delete BEFORE DELETE ON trazabilidad_inspeccion FOR EACH ROW "
        f"BEGIN SELECT RAISE(ABORT, '{MSG_DEL}'); END",
        f"CREATE TRIGGER trg_aud_no_update BEFORE UPDATE ON trazabilidad_eventoauditoria FOR EACH ROW "
        f"BEGIN SELECT RAISE(ABORT, '{MSG_AUD}'); END",
        f"CREATE TRIGGER trg_aud_no_delete BEFORE DELETE ON trazabilidad_eventoauditoria FOR EACH ROW "
        f"BEGIN SELECT RAISE(ABORT, '{MSG_DEL}'); END",
    ]


def crear(apps, schema_editor):
    v = schema_editor.connection.vendor
    for sql in (_mysql() if v == "mysql" else _sqlite() if v == "sqlite" else []):
        schema_editor.execute(sql)


def borrar(apps, schema_editor):
    for t in ("trg_insp_no_update", "trg_insp_no_delete", "trg_aud_no_update", "trg_aud_no_delete"):
        if schema_editor.connection.vendor in ("mysql", "sqlite"):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {t}")


class Migration(migrations.Migration):
    atomic = False  # MariaDB no admite DDL (CREATE TRIGGER) dentro de una transacción
    dependencies = [("trazabilidad", "0001_initial")]
    operations = [migrations.RunPython(crear, borrar)]
