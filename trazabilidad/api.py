import hmac

from rest_framework.exceptions import APIException, AuthenticationFailed, Throttled
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .audit import registrar
from .models import ApiToken
from .services import procesar


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as base
    resp = base(exc, context)
    if resp is not None and isinstance(exc, (AuthenticationFailed, Throttled)):
        registrar(context.get("request")._request if context.get("request") else None,
                  "INGESTA_RECHAZADA", "FALLO", "Inspeccion", origen="API")
    return resp


class TokenThrottle(SimpleRateThrottle):
    scope = "ingesta"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": getattr(request, "api_token_id", "anon")}


class IngestaView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []  # se aplica manualmente tras autenticar el token

    def get_authenticate_header(self, request):
        return "Bearer"  # fuerza HTTP 401 en lugar de 403

    def autenticar(self, request):
        h = request.META.get("HTTP_AUTHORIZATION", "")
        if not h.startswith("Bearer "):
            raise AuthenticationFailed("Token ausente.")
        digest = ApiToken.hash(h[7:].strip())
        for t in ApiToken.objects.filter(activo=True):
            if hmac.compare_digest(t.token_hash, digest):
                return t
        raise AuthenticationFailed("Token inválido.")

    def post(self, request):
        token = self.autenticar(request)
        request.api_token_id = token.pk
        th = TokenThrottle()
        if not th.allow_request(request, self):
            raise Throttled(wait=th.wait())
        status, body = procesar(request.data, request._request)
        return Response(body, status=status)
