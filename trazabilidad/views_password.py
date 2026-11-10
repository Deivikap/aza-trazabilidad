from axes.utils import reset as axes_reset
from django.conf import settings
from django.contrib.auth import get_user_model, views as auth
from django.core.cache import cache
from django.urls import reverse_lazy

from .audit import ip_de, registrar


class SolicitarReset(auth.PasswordResetView):
    """CU-Recuperar contrase\u00f1a, paso 1. Respuesta id\u00e9ntica exista o no la cuenta (anti-enumeraci\u00f3n)."""
    template_name = "trazabilidad/password_reset_form.html"
    email_template_name = "trazabilidad/email/password_reset.txt"
    subject_template_name = "trazabilidad/email/password_reset_asunto.txt"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        ip = ip_de(self.request)
        clave = f"reset:{ip}"
        n = cache.get(clave, 0)
        correo = form.cleaned_data["email"]
        if n >= settings.RESET_MAX_SOLICITUDES_HORA:
            registrar(self.request, "PASSWORD_RESET_SOLICITUD", "FALLO", "Usuario", "", origen="WEB")
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(self.get_success_url())  # misma respuesta, sin enviar correo
        cache.set(clave, n + 1, 3600)
        existe = get_user_model().objects.filter(email__iexact=correo, is_active=True).exists()
        registrar(self.request, "PASSWORD_RESET_SOLICITUD", "EXITO" if existe else "FALLO", "Usuario", "")
        return super().form_valid(form)  # Django solo env\u00eda correo a cuentas activas con contrase\u00f1a utilizable


class ConfirmarReset(auth.PasswordResetConfirmView):
    """CU-Recuperar contrase\u00f1a, paso 2: define la nueva contrase\u00f1a con las mismas pol\u00edticas del sistema."""
    template_name = "trazabilidad/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_valid(self, form):
        resp = super().form_valid(form)
        u = form.user
        axes_reset(username=u.get_username())  # un reset leg\u00edtimo levanta el bloqueo por intentos fallidos
        registrar(self.request, "PASSWORD_RESET_CONFIRMACION", "EXITO", "Usuario", u.pk, usuario=u)
        return resp
