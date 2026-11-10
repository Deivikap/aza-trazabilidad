from .roles import role_of, ADMIN, SUPERVISOR, OPERADOR


def rol(request):
    r = role_of(request.user) if hasattr(request, "user") else None
    return {"rol": r, "es_admin": r == ADMIN, "es_supervisor": r == SUPERVISOR, "es_operador": r == OPERADOR}
