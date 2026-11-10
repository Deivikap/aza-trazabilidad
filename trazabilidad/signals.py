from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .audit import registrar


@receiver(user_logged_in)
def _ok(sender, request, user, **kw):
    registrar(request, "LOGIN", "EXITO", "Usuario", user.pk, usuario=user)


@receiver(user_logged_out)
def _out(sender, request, user, **kw):
    if user:
        registrar(request, "LOGOUT", "EXITO", "Usuario", user.pk, usuario=user)


@receiver(user_login_failed)
def _fail(sender, credentials, request=None, **kw):
    # nunca se registra la contraseña
    registrar(request, "LOGIN", "FALLO", "Usuario", str(credentials.get("username", ""))[:64])
