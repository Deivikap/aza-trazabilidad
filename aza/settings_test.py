from .settings import *  # noqa
import os
# Por defecto SQLite en memoria (rápido). Con DB_ENGINE=mysql se prueba contra MariaDB real
# (usa la base de pruebas test_<DB_NAME>, que Django crea y destruye).
if os.environ.get("DB_ENGINE", "sqlite") != "mysql":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MONGO_URI = "mongomock"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AXES_ENABLED = True
DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}  # sin acceso a BD en la limpieza entre pruebas
