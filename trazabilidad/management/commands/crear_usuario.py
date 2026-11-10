"""Crea un usuario real (producción) con su rol, sin datos de demostración.
Uso: python manage.py crear_usuario jperez --rol ADMIN --email jperez@aza.cl   (pide la clave por consola)
"""
import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from trazabilidad.roles import ADMIN, OPERADOR, ROLES, SUPERVISOR, ensure_groups

# Alias de línea de comandos (ADMIN/SUPERVISOR/OPERADOR) hacia el nombre del grupo.
ALIAS = {"ADMIN": ADMIN, "SUPERVISOR": SUPERVISOR, "OPERADOR": OPERADOR,
         "ADMINISTRADOR": ADMIN}


class Command(BaseCommand):
    help = "Crea un usuario con rol (ADMIN, SUPERVISOR u OPERADOR) cumpliendo la política de contraseñas."

    def add_arguments(self, p):
        p.add_argument("username")
        p.add_argument("--rol", required=True, type=lambda v: ALIAS.get(v.upper(), v), choices=list(ROLES),
                       help="ADMIN, SUPERVISOR u OPERADOR")
        p.add_argument("--email", default="")
        p.add_argument("--password", default=None, help="Si se omite, se solicita por consola sin eco.")

    def handle(self, *a, **o):
        ensure_groups()
        U = get_user_model()
        if U.objects.filter(username=o["username"]).exists():
            raise CommandError("El usuario ya existe.")
        pw = o["password"] or getpass.getpass("Contraseña (mín. 12 caracteres): ")
        try:
            validate_password(pw)
        except ValidationError as e:
            raise CommandError("; ".join(e.messages))
        u = U.objects.create_user(o["username"], o["email"], pw)
        u.groups.add(Group.objects.get(name=o["rol"]))
        self.stdout.write(self.style.SUCCESS(f"Usuario {u.username} creado con rol {o['rol']}."))
