from django.urls import include, path

urlpatterns = [path("", include("trazabilidad.urls"))]
handler403 = "trazabilidad.views_errores.forbidden"
