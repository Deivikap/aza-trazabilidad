from .roles import role_of, ADMIN, SUPERVISOR, OPERADOR
from .security import obtener_config_seguridad


def rol(request):
    r = role_of(request.user) if hasattr(request, "user") else None
    max_int, min_bloq = obtener_config_seguridad()
    return {
        "rol": r,
        "es_admin": r == ADMIN,
        "es_supervisor": r == SUPERVISOR,
        "es_operador": r == OPERADOR,
        "max_intentos_login": max_int,
        "minutos_bloqueo": min_bloq,
    }
