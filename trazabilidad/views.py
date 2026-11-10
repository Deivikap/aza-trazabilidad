import csv
from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import mongo
from .audit import registrar
from .forms import BatchForm, LoteForm, ObservacionForm, RecetaForm, UsuarioForm
from .models import Alarma, Batch, EventoAuditoria, Inspeccion, Lote, Observacion, Receta
from django.conf import settings
from .roles import ADMIN, OPERADOR, ROLES, SUPERVISOR, role_of, role_required

User = get_user_model()
TODOS = ROLES


def turno_de(dt):
    h = timezone.localtime(dt).hour
    return "T1 (06–14)" if 6 <= h < 14 else "T2 (14–22)" if 14 <= h < 22 else "T3 (22–06)"


@role_required(*TODOS)
def dashboard(request):  # CU07 + CU07a
    qs = Inspeccion.objects.all()
    total = qs.count()
    aprob = qs.filter(estado_original="APROBADO").count()
    rech = qs.filter(estado_original="RECHAZADO").count()
    sin = qs.filter(estado_original="SIN_RECETA").count()
    por_turno = defaultdict(lambda: [0, 0])
    for fh, est in qs.values_list("fecha_hora", "estado_original"):
        t = por_turno[turno_de(fh)]
        t[0] += 1
        t[1] += est == "RECHAZADO"
    por_receta = (qs.values("batch__receta__codigo")
                  .annotate(n=Count("id"), r=Count("id", filter=Q(estado_original="RECHAZADO"))).order_by("batch__receta__codigo"))
    ctx = dict(total=total, aprobadas=aprob, rechazadas=rech, sin_receta=sin,
               pct_rechazo=round(100 * rech / total, 1) if total else 0,
               alarmas_abiertas=Alarma.objects.filter(estado="ABIERTA").count(),
               por_turno=[(k, v[0], v[1]) for k, v in sorted(por_turno.items())],
               por_receta=[(x["batch__receta__codigo"] or "— sin receta —", x["n"], x["r"]) for x in por_receta],
               recientes=qs.select_related("batch__lote", "batch__receta")[:6])
    return render(request, "trazabilidad/dashboard.html", ctx)


def _filtrar(request):
    g = request.GET
    qs = Inspeccion.objects.select_related("batch__lote", "batch__receta")
    if g.get("desde"):
        qs = qs.filter(fecha_hora__date__gte=g["desde"])
    if g.get("hasta"):
        qs = qs.filter(fecha_hora__date__lte=g["hasta"])
    if g.get("receta"):
        qs = qs.filter(batch__receta__codigo=g["receta"])
    if g.get("lote"):
        qs = qs.filter(batch__lote__codigo__icontains=g["lote"])
    if g.get("batch"):
        qs = qs.filter(batch__codigo__icontains=g["batch"])
    if g.get("estado") in ("APROBADO", "RECHAZADO", "SIN_RECETA"):
        qs = qs.filter(estado_original=g["estado"])
    return qs


@role_required(*TODOS)
def historial(request):  # CU06
    try:
        pagina = Paginator(_filtrar(request), 20).get_page(request.GET.get("page"))
    except (ValueError, Exception):
        messages.error(request, "Filtros inválidos.")
        pagina = Paginator(Inspeccion.objects.none(), 20).get_page(1)
    q = request.GET.copy(); q.pop("page", None)
    return render(request, "trazabilidad/historial.html", dict(
        pagina=pagina, recetas=Receta.objects.all(), g=request.GET, qs=q.urlencode()))


def _celda(v):
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s  # neutraliza CSV injection


@role_required(SUPERVISOR)
def exportar_csv(request):  # CU13
    qs = _filtrar(request)[: settings.EXPORT_MAX_FILAS + 1]
    filas = list(qs)
    if len(filas) > settings.EXPORT_MAX_FILAS:
        messages.error(request, f"Más de {settings.EXPORT_MAX_FILAS} filas: acota los filtros.")
        return redirect("historial")
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="historial.csv"'
    w = csv.writer(resp)
    w.writerow(["id_externo", "fecha_hora", "lote", "batch", "receta", "medicion_angular", "estado_original"])
    for i in filas:
        w.writerow([_celda(x) for x in (i.id_externo, timezone.localtime(i.fecha_hora).isoformat(), i.batch.lote.codigo,
                                         i.batch.codigo, i.batch.receta.codigo if i.batch.receta else "",
                                         i.medicion_angular, i.estado_original)])
    registrar(request, "EXPORTAR_CSV", "EXITO", "Inspeccion", f"{len(filas)} filas")
    return resp


@role_required(*TODOS)
def detalle(request, pk):  # CU10 + CU08
    insp = get_object_or_404(Inspeccion.objects.select_related("batch__lote", "batch__receta"), pk=pk)
    form = ObservacionForm()
    if request.method == "POST":
        if role_of(request.user) == ADMIN:  # segregación de funciones
            registrar(request, "ACCESO_DENEGADO", "FALLO", "Observacion", pk)
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        form = ObservacionForm(request.POST)
        if form.is_valid():
            o = Observacion.objects.create(inspeccion=insp, usuario=request.user, contenido=form.cleaned_data["contenido"])
            registrar(request, "OBSERVACION_CREADA", "EXITO", "Observacion", o.pk)
            messages.success(request, "Observación registrada.")
            return redirect("detalle", pk=pk)
    return render(request, "trazabilidad/detalle.html", dict(
        i=insp, form=form, observaciones=insp.observaciones.select_related("usuario"),
        payload=mongo.obtener(insp.id_externo) if request.GET.get("payload") else None))


@role_required(*TODOS)
def trazabilidad(request):  # CU05
    lotes = Lote.objects.prefetch_related("batches__receta", "batches__inspecciones").order_by("-fecha_registro")
    return render(request, "trazabilidad/trazabilidad.html", dict(lotes=lotes))


@role_required(OPERADOR, SUPERVISOR)
def alarmas(request):  # CU11
    estado = request.GET.get("estado", "ABIERTA")
    qs = Alarma.objects.select_related("inspeccion__batch__receta", "usuario_rec")
    if estado in ("ABIERTA", "RECONOCIDA"):
        qs = qs.filter(estado=estado)
    return render(request, "trazabilidad/alarmas.html", dict(alarmas=qs[:100], estado=estado))


@role_required(OPERADOR, SUPERVISOR)
@require_POST
def reconocer(request, pk):
    a = get_object_or_404(Alarma, pk=pk)
    if a.estado == "RECONOCIDA":
        messages.info(request, "La alarma ya estaba reconocida.")
    else:
        a.estado, a.usuario_rec, a.fecha_rec = "RECONOCIDA", request.user, timezone.now()
        a.save()
        registrar(request, "ALARMA_RECONOCIDA", "EXITO", "Alarma", a.pk)
        messages.success(request, "Alarma reconocida.")
    return redirect("alarmas")


# ---------------- Administración ----------------
@role_required(ADMIN)
def usuarios(request):  # CU02
    form = UsuarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = form.guardar()
        registrar(request, "USUARIO_CREADO", "EXITO", "Usuario", u.pk)
        messages.success(request, "Usuario creado.")
        return redirect("usuarios")
    lista = [(u, role_of(u)) for u in User.objects.order_by("username")]
    return render(request, "trazabilidad/usuarios.html", dict(lista=lista, form=form))


@role_required(ADMIN)
@require_POST
def usuario_toggle(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u == request.user:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
    else:
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])  # baja lógica: el historial se conserva
        registrar(request, "USUARIO_ACTIVADO" if u.is_active else "USUARIO_DESACTIVADO", "EXITO", "Usuario", u.pk)
    return redirect("usuarios")


@role_required(ADMIN)
@require_POST
def usuario_reset(request, pk):
    """CU-Recuperar contraseña (variante administrada): el Administrador envía el enlace; nunca ve ni fija la clave."""
    from django.contrib.auth.forms import PasswordResetForm
    u = get_object_or_404(User, pk=pk)
    if not u.email or not u.is_active:
        messages.error(request, "La cuenta no tiene correo o está inactiva.")
        registrar(request, "PASSWORD_RESET_ADMIN", "FALLO", "Usuario", u.pk)
    else:
        f = PasswordResetForm({"email": u.email})
        f.is_valid()
        f.save(request=request, email_template_name="trazabilidad/email/password_reset.txt",
               subject_template_name="trazabilidad/email/password_reset_asunto.txt")
        messages.success(request, f"Enlace de restablecimiento enviado a {u.email}.")
        registrar(request, "PASSWORD_RESET_ADMIN", "EXITO", "Usuario", u.pk)
    return redirect("usuarios")


@role_required(ADMIN)
def lotes(request):  # CU03
    fl, fb = LoteForm(prefix="l"), BatchForm(prefix="b")
    if request.method == "POST":
        if "guardar_lote" in request.POST:
            fl = LoteForm(request.POST, prefix="l")
            if fl.is_valid():
                o = fl.save(); registrar(request, "LOTE_CREADO", "EXITO", "Lote", o.pk)
                return redirect("lotes")
        else:
            fb = BatchForm(request.POST, prefix="b")
            if fb.is_valid():
                o = fb.save(); registrar(request, "BATCH_CREADO", "EXITO", "Batch", o.pk)
                return redirect("lotes")
    return render(request, "trazabilidad/lotes.html", dict(
        lotes=Lote.objects.prefetch_related("batches__receta").order_by("-fecha_registro"), fl=fl, fb=fb))


@role_required(ADMIN)
def recetas(request, pk=None):  # CU09
    inst = get_object_or_404(Receta, pk=pk) if pk else None
    form = RecetaForm(request.POST or None, instance=inst)
    if request.method == "POST" and form.is_valid():
        o = form.save()
        registrar(request, "RECETA_ACTUALIZADA" if inst else "RECETA_CREADA", "EXITO", "Receta", o.pk)
        messages.success(request, "Receta guardada. Las inspecciones previas conservan sus límites originales.")
        return redirect("recetas")
    return render(request, "trazabilidad/recetas.html", dict(lista=Receta.objects.all(), form=form, editando=inst))


@role_required(ADMIN)
def auditoria(request):  # CU12
    g = request.GET
    qs = EventoAuditoria.objects.select_related("usuario")
    if g.get("desde"): qs = qs.filter(fecha_hora__date__gte=g["desde"])
    if g.get("hasta"): qs = qs.filter(fecha_hora__date__lte=g["hasta"])
    if g.get("accion"): qs = qs.filter(accion__icontains=g["accion"])
    if g.get("resultado") in ("EXITO", "FALLO"): qs = qs.filter(resultado=g["resultado"])
    if g.get("usuario"): qs = qs.filter(usuario__username__icontains=g["usuario"])
    q = g.copy(); q.pop("page", None)
    return render(request, "trazabilidad/auditoria.html", dict(
        pagina=Paginator(qs, 30).get_page(g.get("page")), g=g, qs=q.urlencode()))


def healthz(request):
    """Sonda de salud para balanceador/Docker: no requiere sesión ni expone detalles internos."""
    from django.db import connection
    from django.http import JsonResponse
    ok = {"mariadb": True, "mongodb": True}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception:
        ok["mariadb"] = False
    try:
        mongo.ping()
    except Exception:
        ok["mongodb"] = False
    return JsonResponse({"estado": "ok" if all(ok.values()) else "degradado", **ok}, status=200 if all(ok.values()) else 503)
