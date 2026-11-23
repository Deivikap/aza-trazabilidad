"""Triggers de base de datos que blindan la inmutabilidad (RF-10, RF-23) incluso ante SQL directo.

MariaDB/MySQL usan SIGNAL; PostgreSQL (Supabase) usa PL/pgSQL RAISE EXCEPTION; SQLite usa RAISE(ABORT).
"""
from django.db import migrations

CAMPOS = ["id_externo", "batch_id", "fecha_hora", "medicion_angular", "estado_original", "limite_min", "limite_max"]
MSG_INSP = "La clasificación y el resultado original de una inspección son inmutables."
MSG_DEL = "Las inspecciones y la bitácora no se eliminan."
MSG_AUD = "La bitácora de auditoría es de solo inserción."


def _mysql():
    cond = " OR ".join(f"NOT (OLD.{c} <=> NEW.{c})" for c in CAMPOS)
    return [
        f"CREATE TRIGGER trg_insp_no_update BEFORE UPDATE ON trazabilidad_inspeccion FOR EACH ROW BEGIN "  # nosec B608
        f"IF {cond} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_INSP}'; END IF; END",
        f"CREATE TRIGGER trg_insp_no_delete BEFORE DELETE ON trazabilidad_inspeccion FOR EACH ROW BEGIN "
        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_DEL}'; END",
        f"CREATE TRIGGER trg_aud_no_update BEFORE UPDATE ON trazabilidad_eventoauditoria FOR EACH ROW BEGIN "  # nosec B608
        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_AUD}'; END",
        f"CREATE TRIGGER trg_aud_no_delete BEFORE DELETE ON trazabilidad_eventoauditoria FOR EACH ROW BEGIN "
        f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{MSG_DEL}'; END",
    ]


def _postgresql():
    cond = " OR ".join(f"OLD.{c} IS DISTINCT FROM NEW.{c}" for c in CAMPOS)
    return [
        f"CREATE OR REPLACE FUNCTION fn_insp_no_update() RETURNS trigger AS $$ BEGIN "  # nosec B608
        f"IF {cond} THEN RAISE EXCEPTION '{MSG_INSP}'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;",
        "DROP TRIGGER IF EXISTS trg_insp_no_update ON trazabilidad_inspeccion;",
        "CREATE TRIGGER trg_insp_no_update BEFORE UPDATE ON trazabilidad_inspeccion "
        "FOR EACH ROW EXECUTE FUNCTION fn_insp_no_update();",
        f"CREATE OR REPLACE FUNCTION fn_no_delete() RETURNS trigger AS $$ BEGIN "  # nosec B608
        f"RAISE EXCEPTION '{MSG_DEL}'; END; $$ LANGUAGE plpgsql;",
        "DROP TRIGGER IF EXISTS trg_insp_no_delete ON trazabilidad_inspeccion;",
        "CREATE TRIGGER trg_insp_no_delete BEFORE DELETE ON trazabilidad_inspeccion "
        "FOR EACH ROW EXECUTE FUNCTION fn_no_delete();",
        f"CREATE OR REPLACE FUNCTION fn_aud_no_update() RETURNS trigger AS $$ BEGIN "  # nosec B608
        f"RAISE EXCEPTION '{MSG_AUD}'; END; $$ LANGUAGE plpgsql;",
        "DROP TRIGGER IF EXISTS trg_aud_no_update ON trazabilidad_eventoauditoria;",
        "CREATE TRIGGER trg_aud_no_update BEFORE UPDATE ON trazabilidad_eventoauditoria "
        "FOR EACH ROW EXECUTE FUNCTION fn_aud_no_update();",
        "DROP TRIGGER IF EXISTS trg_aud_no_delete ON trazabilidad_eventoauditoria;",
        "CREATE TRIGGER trg_aud_no_delete BEFORE DELETE ON trazabilidad_eventoauditoria "
        "FOR EACH ROW EXECUTE FUNCTION fn_no_delete();",
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
    sqls = _mysql() if v == "mysql" else _postgresql() if v == "postgresql" else _sqlite() if v == "sqlite" else []
    for sql in sqls:
        schema_editor.execute(sql)


def borrar(apps, schema_editor):
    v = schema_editor.connection.vendor
    if v in ("mysql", "sqlite"):
        for t in ("trg_insp_no_update", "trg_insp_no_delete", "trg_aud_no_update", "trg_aud_no_delete"):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {t}")
    elif v == "postgresql":
        for stmt in (
            "DROP TRIGGER IF EXISTS trg_insp_no_update ON trazabilidad_inspeccion;",
            "DROP TRIGGER IF EXISTS trg_insp_no_delete ON trazabilidad_inspeccion;",
            "DROP TRIGGER IF EXISTS trg_aud_no_update ON trazabilidad_eventoauditoria;",
            "DROP TRIGGER IF EXISTS trg_aud_no_delete ON trazabilidad_eventoauditoria;",
            "DROP FUNCTION IF EXISTS fn_insp_no_update();",
            "DROP FUNCTION IF EXISTS fn_no_delete();",
            "DROP FUNCTION IF EXISTS fn_aud_no_update();",
        ):
            schema_editor.execute(stmt)


class Migration(migrations.Migration):
    atomic = False  # MariaDB no admite DDL (CREATE TRIGGER) dentro de una transacción
    dependencies = [("trazabilidad", "0001_initial")]
    operations = [migrations.RunPython(crear, borrar)]
