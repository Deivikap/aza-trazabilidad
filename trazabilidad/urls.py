from django.contrib.auth import views as auth
from django.urls import path

from . import views
from .views_password import ConfirmarReset, SolicitarReset
from .api import IngestaView

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("", views.dashboard, name="dashboard"),
    path("login/", auth.LoginView.as_view(template_name="trazabilidad/login.html"), name="login"),
    path("password/recuperar/", SolicitarReset.as_view(), name="password_reset"),
    path("password/recuperar/enviado/", auth.PasswordResetDoneView.as_view(template_name="trazabilidad/password_reset_done.html"), name="password_reset_done"),
    path("password/restablecer/<uidb64>/<token>/", ConfirmarReset.as_view(), name="password_reset_confirm"),
    path("password/restablecida/", auth.PasswordResetCompleteView.as_view(template_name="trazabilidad/password_reset_complete.html"), name="password_reset_complete"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("historial/", views.historial, name="historial"),
    path("historial/exportar/", views.exportar_csv, name="exportar_csv"),
    path("inspecciones/<int:pk>/", views.detalle, name="detalle"),
    path("trazabilidad/", views.trazabilidad, name="trazabilidad"),
    path("alarmas/", views.alarmas, name="alarmas"),
    path("alarmas/<int:pk>/reconocer/", views.reconocer, name="reconocer"),
    path("administracion/usuarios/", views.usuarios, name="usuarios"),
    path("administracion/usuarios/<int:pk>/toggle/", views.usuario_toggle, name="usuario_toggle"),
    path("administracion/usuarios/<int:pk>/reset/", views.usuario_reset, name="usuario_reset"),
    path("administracion/lotes/", views.lotes, name="lotes"),
    path("administracion/recetas/", views.recetas, name="recetas"),
    path("administracion/recetas/<int:pk>/", views.recetas, name="receta_editar"),
    path("administracion/auditoria/", views.auditoria, name="auditoria"),
    path("api/v1/inspecciones/", IngestaView.as_view(), name="api_ingesta"),
]
