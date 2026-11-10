from functools import wraps

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

ADMIN, SUPERVISOR, OPERADOR = "Administrador", "Supervisor", "Operador"
ROLES = (ADMIN, SUPERVISOR, OPERADOR)


def role_of(user):
    if not user.is_authenticated:
        return None
    nombres = set(user.groups.values_list("name", flat=True))
    for r in ROLES:
        if r in nombres:
            return r
    return None


def ensure_groups():
    for r in ROLES:
        Group.objects.get_or_create(name=r)


def role_required(*permitidos):
    """El rol se valida siempre en el servidor (RF-16); si no corresponde, HTTP 403."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **kw):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            if role_of(request.user) not in permitidos:
                from .audit import registrar
                registrar(request, "ACCESO_DENEGADO", "FALLO", entidad=request.path[:50])
                raise PermissionDenied
            return view(request, *a, **kw)
        return wrapper
    return deco
