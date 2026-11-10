from .models import EventoAuditoria


def ip_de(request):
    if request is None:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", ""))[:45]


def registrar(request, accion, resultado, entidad="", registro="", usuario=None, origen=None):
    u = usuario or (request.user if request is not None and request.user.is_authenticated else None)
    return EventoAuditoria.objects.create(
        usuario=u, origen=origen or ("WEB" if request is not None else "SISTEMA"), accion=accion[:80],
        entidad_afectada=entidad[:50], id_registro_afectado=str(registro)[:64],
        resultado=resultado, detalle_ip=ip_de(request))
