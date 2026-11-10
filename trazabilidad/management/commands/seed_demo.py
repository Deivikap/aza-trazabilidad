"""Datos ficticios de demostración: 3 usuarios (uno por rol), lotes, batches, recetas e inspecciones."""
import random
import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from trazabilidad import mongo
from trazabilidad.models import Alarma, ApiToken, Batch, Inspeccion, Lote, Receta
from trazabilidad.roles import ADMIN, OPERADOR, SUPERVISOR, ensure_groups

User = get_user_model()


class Command(BaseCommand):
    help = "Crea datos ficticios de demostración (no usar en producción)."

    def add_arguments(self, p):
        p.add_argument("--password", default=None, help="Contraseña para los 3 usuarios demo (mín. 12). Si se omite, se genera una por usuario.")
        p.add_argument("--n", type=int, default=60)

    def handle(self, *a, **o):
        random.seed(7)
        ensure_groups()
        cred = []
        for username, nombre, rol in (("admin_demo", "Admin Demo", ADMIN), ("supervisor_demo", "Supervisor Demo", SUPERVISOR),
                                      ("operador_demo", "Operador Demo", OPERADOR)):
            pw = o["password"] or secrets.token_urlsafe(12)
            u, _ = User.objects.get_or_create(username=username, defaults=dict(first_name=nombre, email=f"{username}@ejemplo.cl"))
            u.set_password(pw); u.is_active = True; u.save()
            u.groups.set([Group.objects.get(name=rol)])
            cred.append((username, rol, pw))

        recetas = []
        for cod, nom, lo, hi in (("REC-TREF-01", "Alambre 5,5 mm", "-1.500", "1.500"), ("REC-TREF-08", "Alambre 4,0 mm", "-2.000", "2.000"),
                                 ("REC-TREF-12", "Alambre 3,2 mm", "-1.000", "1.000")):
            r, _ = Receta.objects.get_or_create(codigo=cod, defaults=dict(nombre=nom, tol_angular_min=Decimal(lo), tol_angular_max=Decimal(hi)))
            recetas.append(r)
        l1, _ = Lote.objects.get_or_create(codigo="LOTE-TREF-0417")
        l2, _ = Lote.objects.get_or_create(codigo="LOTE-TREF-0418")
        batches = []
        for cod, lote, rec in (("BATCH-TF-71", l1, recetas[0]), ("BATCH-TF-72", l1, recetas[1]), ("BATCH-TF-81", l2, recetas[2]), ("BATCH-TF-82", l2, None)):
            b, _ = Batch.objects.get_or_create(codigo=cod, defaults=dict(lote=lote, receta=rec))
            batches.append(b)

        ahora = timezone.now()
        creadas = 0
        for k in range(o["n"]):
            b = batches[k % len(batches)]
            rec = b.receta
            ang = Decimal(str(round(random.gauss(0, 1.1), 3)))
            if rec is None:
                est = "SIN_RECETA"
            else:
                est = "APROBADO" if rec.tol_angular_min <= ang <= rec.tol_angular_max else "RECHAZADO"
            idx = f"INS-AZA-2026-{k + 1:04d}"
            if Inspeccion.objects.filter(id_externo=idx).exists():
                continue
            fh = ahora - timedelta(hours=random.randint(0, 70), minutes=random.randint(0, 59))  # nosec B311 (datos ficticios de demo, no criptografía)
            i = Inspeccion.objects.create(id_externo=idx, batch=b, fecha_hora=fh, medicion_angular=ang, estado_original=est,
                                          limite_min=rec.tol_angular_min if rec else None, limite_max=rec.tol_angular_max if rec else None)
            try:
                mongo.upsert_payload(idx, dict(lote_codigo=b.lote.codigo, batch_codigo=b.codigo, receta_codigo=rec.codigo if rec else None,
                                               fecha_hora=fh.isoformat(), medicion_angular=float(ang), estado_original=est, origen="seed_demo"))
            except Exception as e:
                self.stderr.write(f"MongoDB no disponible ({e}); se omite el payload crudo.")
            creadas += 1
        sin = Inspeccion.objects.filter(estado_original="SIN_RECETA").first()
        if sin and not Alarma.objects.filter(inspeccion=sin).exists():
            Alarma.objects.create(inspeccion=sin, tipo="SIN_RECETA")
        _, token = ApiToken.crear("camara-simulada")
        self.stdout.write(self.style.SUCCESS(f"Inspecciones creadas: {creadas}"))
        self.stdout.write("Credenciales demo (anótalas, no se vuelven a mostrar):")
        for u, r, pw in cred:
            self.stdout.write(f"  {u:16s} {r:14s} {pw}")
        self.stdout.write(f"Token API del simulador: {token}")
