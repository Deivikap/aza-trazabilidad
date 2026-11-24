"""Política de bloqueo por intentos fallidos configurable por el Administrador (RNF-01)."""
from datetime import timedelta
from django.db import DatabaseError


def obtener_config_seguridad():
    """Devuelve (max_intentos_login, minutos_bloqueo). Fallback seguro (5, 15) antes de migrar."""
    try:
        from .models import ConfiguracionSeguridad
        cfg = ConfiguracionSeguridad.objects.filter(pk=1).first()
        if cfg is not None:
            return cfg.max_intentos_login, cfg.minutos_bloqueo
    except DatabaseError:
        return 5, 15
    return 5, 15


def obtener_limite_intentos(request=None, credentials=None) -> int:
    return obtener_config_seguridad()[0]


def obtener_tiempo_bloqueo(request=None) -> timedelta:
    return timedelta(minutes=obtener_config_seguridad()[1])
