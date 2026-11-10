"""Cabeceras de seguridad adicionales (OWASP A05): CSP estricta, Referrer-Policy y Permissions-Policy."""
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        r = self.get_response(request)
        r.headers.setdefault("Content-Security-Policy", CSP)
        r.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        r.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return r
