import csv
import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, ProtectedError, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import mongo
from .audit import registrar
from .forms import (
    BatchForm, ConfiguracionSeguridadForm, DecisionLoteForm, LoteForm,
    ObservacionForm, RecetaForm, UsuarioEditarForm, UsuarioForm,
)
from .models import Alarma, Batch, ConfiguracionSeguridad, EventoAuditoria, Inspeccion, Lote, Observacion, Receta
from django.conf import settings
from .roles import ADMIN, OPERADOR, ROLES, SUPERVISOR, role_of, role_required

User = get_user_model()
TODOS = ROLES


def turno_de(dt):
    h = timezone.localtime(dt).hour
    return "T1 (06–14)" if 6 <= h < 14 else "T2 (14–22)" if 14 <= h < 22 else "T3 (22–06)"


def _serie_angular(qs, limite=25):
    puntos = list(qs.order_by("-fecha_hora", "-id")[:limite])
    puntos.reverse()
    return [
        {
            "id": i.id_externo,
            "hora": timezone.localtime(i.fecha_hora).strftime("%d/%m %H:%M"),
            "angulo": float(i.medicion_angular),
            "estado": i.estado_original,
            "min": float(i.limite_min) if i.limite_min is not None else None,
            "max": float(i.limite_max) if i.limite_max is not None else None,
        }
        for i in puntos
    ]


@role_required(*TODOS)
def dashboard(request):  # CU07 + CU07a
    qs = Inspeccion.objects.all()
    total = qs.count()
    aprob = qs.filter(estado_original="APROBADO").count()
    rech = qs.filter(estado_original="RECHAZADO").count()
    sin = qs.filter(estado_original="SIN_RECETA").count()
    por_turno = defaultdict(lambda: [0, 0])
    for fh, est in qs.values_list("fecha_hora", "estado_original").iterator(chunk_size=2000):
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
               recientes=qs.select_related("batch__lote", "batch__receta")[:6],
               chart_estados={"aprobadas": aprob, "rechazadas": rech, "sin_receta": sin},
               chart_angulo=_serie_angular(qs, 25))
    return render(request, "trazabilidad/dashboard.html", ctx)


@role_required(SUPERVISOR, ADMIN)
def informe_gestion(request):
    """Informe de gestión ejecutable y visualizable directamente desde la plataforma."""
    g = request.GET
    qs = Inspeccion.objects.select_related("batch__lote", "batch__receta")
    try:
        qs = _rango_fechas(qs, g, "fecha_hora")
    except ValueError:
        messages.error(request, "Fechas inválidas: usa el formato AAAA-MM-DD.")
        qs = qs.none()
    if g.get("receta"):
        qs = qs.filter(batch__receta__codigo=g["receta"])
    if g.get("lote"):
        qs = qs.filter(batch__lote__codigo__icontains=g["lote"])

    total = qs.count()
    aprob = qs.filter(estado_original="APROBADO").count()
    rech = qs.filter(estado_original="RECHAZADO").count()
    sin = qs.filter(estado_original="SIN_RECETA").count()
    pct_aprob = round(100 * aprob / total, 1) if total else 0
    pct_rech = round(100 * rech / total, 1) if total else 0
    pct_sin = round(100 * sin / total, 1) if total else 0

    stats_ang = qs.aggregate(
        prom=Avg("medicion_angular"),
        minimo=Min("medicion_angular"),
        maximo=Max("medicion_angular"),
    )

    turnos_map = defaultdict(lambda: [0, 0, 0, 0])  # total, aprob, rech, sin
    for fh, est in qs.values_list("fecha_hora", "estado_original").iterator(chunk_size=2000):
        t = turnos_map[turno_de(fh)]
        t[0] += 1
        if est == "APROBADO":
            t[1] += 1
        elif est == "RECHAZADO":
            t[2] += 1
        else:
            t[3] += 1
    por_turno = [
        {
            "turno": k, "total": v[0], "aprobadas": v[1], "rechazadas": v[2], "sin_receta": v[3],
            "pct_rechazo": round(100 * v[2] / v[0], 1) if v[0] else 0,
        }
        for k, v in sorted(turnos_map.items())
    ]

    recetas_agg = (
        qs.values("batch__receta__codigo", "batch__receta__nombre",
                  "batch__receta__tol_angular_min", "batch__receta__tol_angular_max")
        .annotate(
            total=Count("id"),
            aprobadas=Count("id", filter=Q(estado_original="APROBADO")),
            rechazadas=Count("id", filter=Q(estado_original="RECHAZADO")),
        )
        .order_by("batch__receta__codigo")
    )
    por_receta = [
        {
            "codigo": x["batch__receta__codigo"] or "— sin receta —",
            "nombre": x["batch__receta__nombre"] or "Batch sin receta asignada",
            "tol_min": x["batch__receta__tol_angular_min"],
            "tol_max": x["batch__receta__tol_angular_max"],
            "total": x["total"],
            "aprobadas": x["aprobadas"],
            "rechazadas": x["rechazadas"],
            "pct_rechazo": round(100 * x["rechazadas"] / x["total"], 1) if x["total"] else 0,
        }
        for x in recetas_agg
    ]

    lotes_agg = (
        qs.values("batch__lote__codigo", "batch__lote__estado", "batch__lote__decision_supervisor")
        .annotate(
            batches=Count("batch_id", distinct=True),
            total=Count("id"),
            aprobadas=Count("id", filter=Q(estado_original="APROBADO")),
            rechazadas=Count("id", filter=Q(estado_original="RECHAZADO")),
        )
        .order_by("-total", "batch__lote__codigo")
    )
    por_lote = [
        {
            "codigo": x["batch__lote__codigo"],
            "estado": x["batch__lote__estado"],
            "decision": x["batch__lote__decision_supervisor"],
            "batches": x["batches"],
            "total": x["total"],
            "aprobadas": x["aprobadas"],
            "rechazadas": x["rechazadas"],
            "pct_rechazo": round(100 * x["rechazadas"] / x["total"], 1) if x["total"] else 0,
        }
        for x in lotes_agg
    ]

    alarmas_qs = Alarma.objects.filter(inspeccion__in=qs).select_related("inspeccion__batch", "usuario_rec")
    alarmas_total = alarmas_qs.count()
    alarmas_abiertas = alarmas_qs.filter(estado="ABIERTA").count()
    alarmas_reconocidas = alarmas_qs.filter(estado="RECONOCIDA").count()
    observaciones = (
        Observacion.objects.filter(inspeccion__in=qs)
        .select_related("inspeccion__batch__lote", "usuario")
        .order_by("-fecha_hora")[:12]
    )

    q = g.copy()
    q.pop("page", None)
    registrar(request, "INFORME_GESTION_CONSULTADO", "EXITO", "InformeGestion", f"{total} inspecciones")

    ctx = dict(
        g=g,
        qs_params=q.urlencode(),
        recetas=Receta.objects.all(),
        generado_en=timezone.localtime(),
        total=total,
        aprobadas=aprob,
        rechazadas=rech,
        sin_receta=sin,
        pct_aprobacion=pct_aprob,
        pct_rechazo=pct_rech,
        pct_sin_receta=pct_sin,
        stats_ang=stats_ang,
        por_turno=por_turno,
        por_receta=por_receta,
        por_lote=por_lote,
        alarmas_total=alarmas_total,
        alarmas_abiertas=alarmas_abiertas,
        alarmas_reconocidas=alarmas_reconocidas,
        alarmas_lista=alarmas_qs[:10],
        observaciones=observaciones,
        chart_estados={"aprobadas": aprob, "rechazadas": rech, "sin_receta": sin},
        chart_angulo=_serie_angular(qs, 40),
        chart_turnos=[{"turno": x["turno"], "total": x["total"], "rechazadas": x["rechazadas"]} for x in por_turno],
    )
    return render(request, "trazabilidad/informe_gestion.html", ctx)


def _inicio_dia(texto):
    """'YYYY-MM-DD' -> medianoche local (aware). ValueError si no es una fecha real."""
    d = datetime.strptime(texto, "%Y-%m-%d").date()
    return timezone.make_aware(datetime.combine(d, time.min))


def _rango_fechas(qs, g, campo):
    """Filtra por día local con un rango [desde, hasta+1d) en vez de __date: no depende de las tablas
    de zonas horarias de MariaDB (CONVERT_TZ devuelve NULL si no están cargadas) y aprovecha el índice."""
    if g.get("desde"):
        qs = qs.filter(**{f"{campo}__gte": _inicio_dia(g["desde"])})
    if g.get("hasta"):
        qs = qs.filter(**{f"{campo}__lt": _inicio_dia(g["hasta"]) + timedelta(days=1)})
    return qs


def _filtrar(request):
    g = request.GET
    qs = _rango_fechas(Inspeccion.objects.select_related("batch__lote", "batch__receta"), g, "fecha_hora")
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
    try:
        filas = list(_filtrar(request)[: settings.EXPORT_MAX_FILAS + 1])
    except ValueError:
        messages.error(request, "Fechas inválidas: usa el formato AAAA-MM-DD.")
        return redirect("historial")
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
    mostrar_payload = bool(request.GET.get("payload"))
    payload = None
    payload_error = False
    if mostrar_payload:
        try:
            payload = mongo.obtener(insp.id_externo)
        except Exception:
            payload_error = True
    payload_json = json.dumps(payload, indent=2, ensure_ascii=False, default=str) if payload is not None else None
    return render(request, "trazabilidad/detalle.html", dict(
        i=insp, form=form, observaciones=insp.observaciones.select_related("usuario"),
        payload=payload, payload_json=payload_json, mostrar_payload=mostrar_payload, payload_error=payload_error))


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


@role_required(SUPERVISOR, ADMIN)
def rendimiento(request):
    """Panel de rendimiento operativo por turno y por operador/supervisor (diario, semanal, mensual)."""
    periodos = {
        "diario": ("Diario (últimas 24 h)", timedelta(days=1)),
        "semanal": ("Semanal (últimos 7 días)", timedelta(days=7)),
        "mensual": ("Mensual (últimos 30 días)", timedelta(days=30)),
    }
    periodo = request.GET.get("periodo", "semanal")
    if periodo not in periodos:
        periodo = "semanal"
    etiqueta_periodo, delta = periodos[periodo]
    ahora = timezone.now()
    desde = ahora - delta

    # Resumen comparativo de los 3 horizontes (diario, semanal, mensual)
    resumen_horizontes = []
    for clave, (etiq, dlt) in periodos.items():
        q_h = Inspeccion.objects.filter(fecha_hora__gte=ahora - dlt)
        tot_h = q_h.count()
        apr_h = q_h.filter(estado_original="APROBADO").count()
        rec_h = q_h.filter(estado_original="RECHAZADO").count()
        resumen_horizontes.append({
            "clave": clave,
            "etiqueta": etiq,
            "total": tot_h,
            "aprobadas": apr_h,
            "rechazadas": rec_h,
            "efectividad": round(100 * apr_h / tot_h, 1) if tot_h else 0,
        })

    # Efectividad por turno en el período seleccionado
    turnos_orden = ["T1 (06–14)", "T2 (14–22)", "T3 (22–06)"]
    t_stats = {t: {"total": 0, "aprobadas": 0, "rechazadas": 0, "sin_receta": 0, "alarmas": 0, "alarmas_rec": 0}
               for t in turnos_orden}
    qs_insp = Inspeccion.objects.filter(fecha_hora__gte=desde)
    for fh, est in qs_insp.values_list("fecha_hora", "estado_original").iterator(chunk_size=2000):
        t = t_stats[turno_de(fh)]
        t["total"] += 1
        if est == "APROBADO":
            t["aprobadas"] += 1
        elif est == "RECHAZADO":
            t["rechazadas"] += 1
        else:
            t["sin_receta"] += 1

    qs_alarmas = Alarma.objects.filter(fecha_hora__gte=desde).select_related("usuario_rec")
    for al in qs_alarmas:
        t = t_stats[turno_de(al.fecha_hora)]
        t["alarmas"] += 1
        if al.estado == "RECONOCIDA":
            t["alarmas_rec"] += 1

    por_turno = []
    for nombre in turnos_orden:
        st = t_stats[nombre]
        ef = round(100 * st["aprobadas"] / st["total"], 1) if st["total"] else 0
        pr = round(100 * st["rechazadas"] / st["total"], 1) if st["total"] else 0
        por_turno.append({
            "turno": nombre,
            **st,
            "efectividad": ef,
            "pct_rechazo": pr,
        })

    # Comparativa por Operador y Supervisor en sus turnos (gestiones reales en el período)
    personal = []
    usuarios_op_sup = [
        (u, role_of(u)) for u in User.objects.filter(is_active=True).order_by("username")
        if role_of(u) in (OPERADOR, SUPERVISOR)
    ]
    obs_periodo = list(Observacion.objects.filter(fecha_hora__gte=desde).select_related("usuario"))
    alarmas_rec_periodo = list(
        Alarma.objects.filter(estado="RECONOCIDA", fecha_rec__gte=desde, usuario_rec__isnull=False)
        .select_related("usuario_rec")
    )
    lotes_dec_periodo = list(
        Lote.objects.filter(fecha_decision__gte=desde, supervisor_decision__isnull=False)
        .select_related("supervisor_decision")
    )

    for u, r_u in usuarios_op_sup:
        obs_u = [o for o in obs_periodo if o.usuario_id == u.pk]
        al_u = [a for a in alarmas_rec_periodo if a.usuario_rec_id == u.pk]
        lot_u = [l for l in lotes_dec_periodo if l.supervisor_decision_id == u.pk]

        conteo_turnos = defaultdict(int)
        for o in obs_u:
            conteo_turnos[turno_de(o.fecha_hora)] += 1
        for a in al_u:
            conteo_turnos[turno_de(a.fecha_rec)] += 1
        for l in lot_u:
            conteo_turnos[turno_de(l.fecha_decision)] += 1

        tiempos_min = [
            max(0.0, (a.fecha_rec - a.fecha_hora).total_seconds() / 60.0)
            for a in al_u if a.fecha_rec and a.fecha_hora
        ]
        tiempo_prom = round(sum(tiempos_min) / len(tiempos_min), 1) if tiempos_min else None
        turno_principal = max(conteo_turnos.items(), key=lambda kv: kv[1])[0] if conteo_turnos else "Sin gestiones"
        ef_turno = next((x["efectividad"] for x in por_turno if x["turno"] == turno_principal), None)
        acciones_tot = len(obs_u) + len(al_u) + len(lot_u)
        personal.append({
            "usuario": u.username,
            "nombre": u.get_full_name() or u.username,
            "rol": r_u,
            "turno_principal": turno_principal,
            "observaciones": len(obs_u),
            "alarmas_rec": len(al_u),
            "lotes_decididos": len(lot_u),
            "acciones_total": acciones_tot,
            "tiempo_prom_min": tiempo_prom,
            "efectividad_turno": ef_turno,
        })
    personal.sort(key=lambda x: (-x["acciones_total"], x["rol"], x["usuario"]))

    chart_efectividad = [
        {"turno": x["turno"], "efectividad": x["efectividad"], "aprobadas": x["aprobadas"], "total": x["total"]}
        for x in por_turno
    ]
    return render(request, "trazabilidad/rendimiento.html", dict(
        periodo=periodo,
        etiqueta_periodo=etiqueta_periodo,
        resumen_horizontes=resumen_horizontes,
        por_turno=por_turno,
        personal=personal,
        chart_efectividad=chart_efectividad,
    ))


@role_required(SUPERVISOR)
def revision_lotes(request):
    """Vista exclusiva del Supervisor para revisar indicadores por lote y aprobar o rechazar lotes."""
    lotes_qs = Lote.objects.select_related("supervisor_decision").prefetch_related("batches__receta").order_by("-fecha_registro")
    filas = []
    for l in lotes_qs:
        insps = Inspeccion.objects.filter(batch__lote=l)
        tot = insps.count()
        apr = insps.filter(estado_original="APROBADO").count()
        rec = insps.filter(estado_original="RECHAZADO").count()
        sin = insps.filter(estado_original="SIN_RECETA").count()
        filas.append({
            "lote": l,
            "batches": l.batches.count(),
            "total": tot,
            "aprobadas": apr,
            "rechazadas": rec,
            "sin_receta": sin,
            "pct_rechazo": round(100 * rec / tot, 1) if tot else 0,
            "efectividad": round(100 * apr / tot, 1) if tot else 0,
        })
    return render(request, "trazabilidad/revision_lotes.html", dict(filas=filas))


@role_required(SUPERVISOR)
@require_POST
def lote_decidir(request, pk):
    """El Supervisor aprueba o rechaza formalmente un lote (sin alterar clasificaciones individuales de cámara)."""
    lote = get_object_or_404(Lote, pk=pk)
    form = DecisionLoteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Decisión inválida sobre el lote.")
        return redirect("revision_lotes")
    dec = form.cleaned_data["decision"]
    lote.decision_supervisor = dec
    lote.supervisor_decision = request.user
    lote.fecha_decision = timezone.now()
    lote.comentario_decision = form.cleaned_data["comentario"]
    lote.save(update_fields=["decision_supervisor", "supervisor_decision", "fecha_decision", "comentario_decision"])
    accion = "LOTE_APROBADO" if dec == "APROBADO" else "LOTE_RECHAZADO"
    registrar(request, accion, "EXITO", "Lote", lote.codigo)
    messages.success(request, f"Lote {lote.codigo} marcado como {lote.get_decision_supervisor_display()}.")
    return redirect("revision_lotes")


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
    cfg = ConfiguracionSeguridad.actual()
    return render(request, "trazabilidad/usuarios.html", dict(
        lista=lista, form=form, editando=None,
        cfg_form=ConfiguracionSeguridadForm(instance=cfg), cfg_seg=cfg))


@role_required(ADMIN)
def usuario_editar(request, pk):  # CU02 (Actualizar)
    u = get_object_or_404(User, pk=pk)
    inicial = {"first_name": u.first_name, "email": u.email, "rol": role_of(u) or OPERADOR}
    form = UsuarioEditarForm(request.POST or None, initial=inicial, instance=u)
    if request.method == "POST" and form.is_valid():
        if u == request.user and form.cleaned_data["rol"] != ADMIN:
            messages.error(request, "No puedes quitar tu propio rol de Administrador.")
        else:
            form.guardar()
            registrar(request, "USUARIO_ACTUALIZADO", "EXITO", "Usuario", u.pk)
            messages.success(request, f"Usuario {u.username} actualizado.")
            return redirect("usuarios")
    lista = [(usr, role_of(usr)) for usr in User.objects.order_by("username")]
    cfg = ConfiguracionSeguridad.actual()
    return render(request, "trazabilidad/usuarios.html", dict(
        lista=lista, form=form, editando=u,
        cfg_form=ConfiguracionSeguridadForm(instance=cfg), cfg_seg=cfg))


@role_required(ADMIN)
@require_POST
def config_seguridad(request):
    """Permite al Administrador ajustar el límite de intentos fallidos (3–10) y minutos de bloqueo (5–120)."""
    cfg = ConfiguracionSeguridad.actual()
    form = ConfiguracionSeguridadForm(request.POST, instance=cfg)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.actualizado_por = request.user
        obj.save()
        registrar(
            request, "CONFIG_SEGURIDAD_ACTUALIZADA", "EXITO", "ConfiguracionSeguridad",
            f"intentos={obj.max_intentos_login},bloqueo={obj.minutos_bloqueo}m",
        )
        messages.success(
            request,
            f"Política de bloqueo actualizada: {obj.max_intentos_login} intentos fallidos / {obj.minutos_bloqueo} minutos.",
        )
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
        registrar(request, "CONFIG_SEGURIDAD_ACTUALIZADA", "FALLO", "ConfiguracionSeguridad", "valores_invalidos")
    return redirect("usuarios")


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


def _render_lotes(request, fl, fb, editando_lote=None, editando_batch=None):
    return render(request, "trazabilidad/lotes.html", dict(
        lotes=Lote.objects.prefetch_related("batches__receta").order_by("-fecha_registro"),
        batches=Batch.objects.select_related("lote", "receta").order_by("-fecha_registro"),
        fl=fl, fb=fb, editando_lote=editando_lote, editando_batch=editando_batch))


@role_required(ADMIN)
def lotes(request):  # CU03
    fl, fb = LoteForm(prefix="l"), BatchForm(prefix="b")
    if request.method == "POST":
        if "guardar_lote" in request.POST:
            fl = LoteForm(request.POST, prefix="l")
            if fl.is_valid():
                o = fl.save(); registrar(request, "LOTE_CREADO", "EXITO", "Lote", o.pk)
                messages.success(request, f"Lote {o.codigo} creado.")
                return redirect("lotes")
        else:
            fb = BatchForm(request.POST, prefix="b")
            if fb.is_valid():
                o = fb.save(); registrar(request, "BATCH_CREADO", "EXITO", "Batch", o.pk)
                messages.success(request, f"Batch {o.codigo} creado.")
                return redirect("lotes")
    return _render_lotes(request, fl, fb)


@role_required(ADMIN)
def lote_editar(request, pk):  # CU03 (Actualizar lote)
    inst = get_object_or_404(Lote, pk=pk)
    fl = LoteForm(request.POST or None, prefix="l", instance=inst)
    if request.method == "POST" and fl.is_valid():
        o = fl.save()
        registrar(request, "LOTE_ACTUALIZADO", "EXITO", "Lote", o.pk)
        messages.success(request, f"Lote {o.codigo} actualizado.")
        return redirect("lotes")
    return _render_lotes(request, fl, BatchForm(prefix="b"), editando_lote=inst)


@role_required(ADMIN)
@require_POST
def lote_eliminar(request, pk):  # CU03 (Eliminar lote respetando ON DELETE RESTRICT)
    inst = get_object_or_404(Lote, pk=pk)
    codigo = inst.codigo
    try:
        inst.delete()
        registrar(request, "LOTE_ELIMINADO", "EXITO", "Lote", codigo)
        messages.success(request, f"Lote {codigo} eliminado.")
    except ProtectedError:
        registrar(request, "LOTE_ELIMINACION_BLOQUEADA", "FALLO", "Lote", codigo)
        messages.error(request, f"No se puede eliminar el lote {codigo} porque tiene batches asociados (ON DELETE RESTRICT). Puedes cerrarlo editando su estado.")
    return redirect("lotes")


@role_required(ADMIN)
def batch_editar(request, pk):  # CU03 (Actualizar batch)
    inst = get_object_or_404(Batch, pk=pk)
    fb = BatchForm(request.POST or None, prefix="b", instance=inst)
    if request.method == "POST" and fb.is_valid():
        o = fb.save()
        registrar(request, "BATCH_ACTUALIZADO", "EXITO", "Batch", o.pk)
        messages.success(request, f"Batch {o.codigo} actualizado.")
        return redirect("lotes")
    return _render_lotes(request, LoteForm(prefix="l"), fb, editando_batch=inst)


@role_required(ADMIN)
@require_POST
def batch_eliminar(request, pk):  # CU03 (Eliminar batch respetando ON DELETE RESTRICT)
    inst = get_object_or_404(Batch, pk=pk)
    codigo = inst.codigo
    try:
        inst.delete()
        registrar(request, "BATCH_ELIMINADO", "EXITO", "Batch", codigo)
        messages.success(request, f"Batch {codigo} eliminado.")
    except ProtectedError:
        registrar(request, "BATCH_ELIMINACION_BLOQUEADA", "FALLO", "Batch", codigo)
        messages.error(request, f"No se puede eliminar el batch {codigo} porque tiene inspecciones asociadas (ON DELETE RESTRICT). Puedes marcarlo como Finalizado.")
    return redirect("lotes")


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
@require_POST
def receta_eliminar(request, pk):  # CU09 (Eliminar receta respetando ON DELETE RESTRICT)
    inst = get_object_or_404(Receta, pk=pk)
    codigo = inst.codigo
    try:
        inst.delete()
        registrar(request, "RECETA_ELIMINADA", "EXITO", "Receta", codigo)
        messages.success(request, f"Receta {codigo} eliminada.")
    except ProtectedError:
        registrar(request, "RECETA_ELIMINACION_BLOQUEADA", "FALLO", "Receta", codigo)
        messages.error(request, f"No se puede eliminar la receta {codigo} porque está asociada a uno o más batches (ON DELETE RESTRICT). Desactívala editando el campo Activa.")
    return redirect("recetas")


@role_required(ADMIN)
def auditoria(request):  # CU12
    g = request.GET
    qs = EventoAuditoria.objects.select_related("usuario")
    try:
        qs = _rango_fechas(qs, g, "fecha_hora")
    except ValueError:
        messages.error(request, "Fechas inválidas: usa el formato AAAA-MM-DD.")
        qs = qs.none()
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
