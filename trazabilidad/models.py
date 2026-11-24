import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Receta(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=100)
    tol_angular_min = models.DecimalField(max_digits=6, decimal_places=3)
    tol_angular_max = models.DecimalField(max_digits=6, decimal_places=3)
    activa = models.BooleanField(default=True, db_index=True)

    def clean(self):
        if self.tol_angular_min is not None and self.tol_angular_max is not None \
                and self.tol_angular_min >= self.tol_angular_max:
            raise ValidationError("La tolerancia mínima debe ser menor que la máxima.")

    def __str__(self):
        return f"{self.codigo} – {self.nombre}"


class Lote(models.Model):
    ESTADOS = [("ACTIVO", "Activo"), ("CERRADO", "Cerrado")]
    ESTADOS_REVISION = [("PENDIENTE", "Pendiente"), ("APROBADO", "Aprobado"), ("RECHAZADO", "Rechazado")]
    codigo = models.CharField(max_length=50, unique=True)
    fecha_registro = models.DateTimeField(auto_now_add=True, db_index=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="ACTIVO")
    decision_supervisor = models.CharField(max_length=12, choices=ESTADOS_REVISION, default="PENDIENTE", db_index=True)
    supervisor_decision = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="lotes_revisados"
    )
    fecha_decision = models.DateTimeField(null=True, blank=True)
    comentario_decision = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return self.codigo


class Batch(models.Model):
    ESTADOS = [("EN_PROCESO", "En proceso"), ("FIN", "Finalizado")]
    codigo = models.CharField(max_length=50, unique=True)
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="batches")
    receta = models.ForeignKey(Receta, on_delete=models.PROTECT, null=True, blank=True, related_name="batches")
    fecha_registro = models.DateTimeField(auto_now_add=True, db_index=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default="EN_PROCESO")

    def __str__(self):
        return self.codigo


class Inspeccion(models.Model):
    """Resultado emitido por la cámara. La clasificación original es inmutable (RF-10)."""
    ESTADOS = [("APROBADO", "Aprobado"), ("RECHAZADO", "Rechazado"), ("SIN_RECETA", "Sin receta")]
    PROTEGIDOS = ("id_externo", "batch_id", "fecha_hora", "medicion_angular", "estado_original", "limite_min", "limite_max")

    id_externo = models.CharField(max_length=64, unique=True)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="inspecciones")
    fecha_hora = models.DateTimeField()
    medicion_angular = models.DecimalField(max_digits=6, decimal_places=3)
    estado_original = models.CharField(max_length=12, choices=ESTADOS)
    fecha_recepcion = models.DateTimeField(auto_now_add=True)
    limite_min = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)  # snapshot (RF-25)
    limite_max = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "-fecha_hora"], name="idx_insp_batch_fecha"),      # trazabilidad por batch (CU05)
            models.Index(fields=["fecha_hora"], name="idx_insp_fecha"),                    # historial por rango de fechas (CU06)
            models.Index(fields=["estado_original", "fecha_hora"], name="idx_insp_estado_fecha"),  # filtro por estado + fechas
        ]
        ordering = ["-fecha_hora"]

    def save(self, *args, **kwargs):
        if self.pk:
            actual = Inspeccion.objects.get(pk=self.pk)
            for campo in self.PROTEGIDOS:
                if getattr(actual, campo) != getattr(self, campo):
                    raise ValidationError("La clasificación y el resultado original son inmutables.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Las inspecciones no se eliminan.")

    def __str__(self):
        return self.id_externo


class Observacion(models.Model):
    inspeccion = models.ForeignKey(Inspeccion, on_delete=models.PROTECT, related_name="observaciones")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    contenido = models.CharField(max_length=500)
    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)


class EventoAuditoria(models.Model):
    """Bitácora append-only (RF-15, RF-23)."""
    RESULTADOS = [("EXITO", "Éxito"), ("FALLO", "Fallo")]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    origen = models.CharField(max_length=60)
    accion = models.CharField(max_length=80, db_index=True)
    entidad_afectada = models.CharField(max_length=50, blank=True)
    id_registro_afectado = models.CharField(max_length=64, blank=True)
    resultado = models.CharField(max_length=5, choices=RESULTADOS)
    detalle_ip = models.CharField(max_length=45, blank=True)
    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha_hora", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("EventoAuditoria es de solo inserción.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("EventoAuditoria es de solo inserción.")


class Alarma(models.Model):
    TIPOS = [("SIN_RECETA", "Batch sin receta"), ("RECHAZOS_SEGUIDOS", "Rechazos consecutivos")]
    ESTADOS = [("ABIERTA", "Abierta"), ("RECONOCIDA", "Reconocida")]
    inspeccion = models.ForeignKey(Inspeccion, on_delete=models.PROTECT, related_name="alarmas")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    estado = models.CharField(max_length=12, choices=ESTADOS, default="ABIERTA")
    fecha_hora = models.DateTimeField(auto_now_add=True)
    usuario_rec = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    fecha_rec = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_hora"]
        indexes = [models.Index(fields=["estado", "-fecha_hora"], name="idx_alarma_estado_fecha")]


class ApiToken(models.Model):
    """Credencial M2M del sistema de inspección. Solo se guarda el hash SHA-256."""
    nombre = models.CharField(max_length=60)
    token_hash = models.CharField(max_length=64, unique=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def crear(cls, nombre: str):
        token = secrets.token_urlsafe(32)
        obj = cls.objects.create(nombre=nombre, token_hash=cls.hash(token))
        return obj, token


class ConfiguracionSeguridad(models.Model):
    """Parámetros de bloqueo por intentos fallidos (RNF-01) administrables por el rol Administrador."""
    max_intentos_login = models.PositiveSmallIntegerField(default=5)
    minutos_bloqueo = models.PositiveSmallIntegerField(default=15)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.max_intentos_login is None or not (3 <= self.max_intentos_login <= 10):
            raise ValidationError("El límite de intentos fallidos debe estar entre 3 y 10.")
        if self.minutos_bloqueo is None or not (5 <= self.minutos_bloqueo <= 120):
            raise ValidationError("El tiempo de bloqueo debe estar entre 5 y 120 minutos.")

    @classmethod
    def actual(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"max_intentos_login": 5, "minutos_bloqueo": 15})
        return obj
