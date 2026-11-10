# Pruebas y calidad

```bash
pytest -v                                    # SQLite en memoria + MongoDB simulado (mongomock)
DB_ENGINE=mysql DB_USER=... DB_PASSWORD=... pytest -v    # contra MariaDB real (crea y destruye test_<DB_NAME>)
pytest --cov=trazabilidad --cov-report=term  # cobertura
bandit -r trazabilidad aza -x trazabilidad/tests
pip-audit -r requirements.txt
bash deploy/prueba_respaldo_mariadb.sh       # respaldo cifrado y restauración de MariaDB
bash tools/benchmark_indices.sh              # 300 000 filas: consultas del historial antes/después de la migración 0003
python tools/capturas_responsive.py          # responsive 1920/768/390 px (Playwright, servidor en :8765)
python tools/accesibilidad_axe.py            # axe-core WCAG 2.1 A/AA sobre 8 pantallas
locust -f loadtest/locustfile.py --headless -u 20 -r 5 -t 60s --host http://127.0.0.1:8000 --csv evidencias/locust_20u
```
Para la carga contra gunicorn sin TLS use `DJANGO_DEBUG=0 DJANGO_SSL_REDIRECT=0 DJANGO_COOKIES_SECURE=0 INGESTA_RATE=100000/min`. **Nunca** use esas variables en producción.

Las evidencias de la última ejecución están en `evidencias/`. La prueba de concurrencia solo se ejecuta con MariaDB y se omite en SQLite. MongoDB real no se pudo ejecutar en el entorno de desarrollo; sus pruebas usan `mongomock` y quedan pendientes de repetir con `docker compose` (ver `docs/DESPLIEGUE.md`).
