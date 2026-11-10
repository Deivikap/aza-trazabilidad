import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-cambiar-en-produccion")
if not DEBUG and (SECRET_KEY.startswith("dev-only") or SECRET_KEY.startswith("cambia-esto") or len(SECRET_KEY) < 40):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("Define DJANGO_SECRET_KEY (>=40 caracteres aleatorios) cuando DJANGO_DEBUG=0.")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "axes", "trazabilidad",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "trazabilidad.middleware.SecurityHeadersMiddleware",
    "axes.middleware.AxesMiddleware",
]
ROOT_URLCONF = "aza.urls"
WSGI_APPLICATION = "aza.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "trazabilidad.context.rol"]},
}]

# --- MariaDB (relacional, fuente de verdad) ---------------------------------
if os.environ.get("DB_ENGINE", "sqlite") == "mysql":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "aza_trazabilidad"),
        "USER": os.environ.get("DB_USER", "aza_app"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }}
else:  # solo para desarrollo rápido / pruebas
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# --- MongoDB (payload JSON crudo) ------------------------------------------
# Por defecto "mongomock" (en memoria) para arrancar sin servidores; con Docker se usa mongodb://mongo:27017
MONGO_URI = os.environ.get("MONGO_URI", "mongomock")
MONGO_DB = os.environ.get("MONGO_DB", "aza_trazabilidad")

# --- Seguridad ---------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # horas = 15 minutos
AXES_LOCKOUT_TEMPLATE = "trazabilidad/bloqueado.html"
AXES_RESET_ON_SUCCESS = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 30        # RNF-01: expira tras 30 minutos de inactividad
SESSION_SAVE_EVERY_REQUEST = True    # cada petición renueva el plazo (inactividad, no duración absoluta)
CSRF_COOKIE_HTTPONLY = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    # Solo para bancos de prueba sin TLS (p. ej. carga local por HTTP); en producción debe quedar en 1.
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = os.environ.get("DJANGO_COOKIES_SECURE", "1") == "1"
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") == "1"
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_REFERRER_POLICY = "same-origin"
if os.environ.get("TRUST_PROXY", "0") == "1":  # detrás de Caddy/Nginx que termina TLS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {"ingesta": os.environ.get("INGESTA_RATE", "60/min")},
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "trazabilidad.api.exception_handler",
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_aza"}
          if os.environ.get("DB_ENGINE", "sqlite") == "mysql" else
          {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Recuperación de contraseña: enlace de un solo uso con vigencia de 1 hora.
# En desarrollo el correo se imprime en la consola del servidor; en producción configurar SMTP por variables de entorno.
PASSWORD_RESET_TIMEOUT = 3600
RESET_MAX_SOLICITUDES_HORA = int(os.environ.get("RESET_MAX_SOLICITUDES_HORA", "5"))
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-responder@aza.local")

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Reglas de negocio configurables
ALARMA_RECHAZOS_SEGUIDOS = 3
EXPORT_MAX_FILAS = 10000
