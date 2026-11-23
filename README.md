# Plataforma de Gestión y Trazabilidad de Inspecciones – Aceros AZA (demo funcional)

Django 5.2 LTS · DRF · MariaDB 11.4 (fuente de verdad) · MongoDB 7.0 (payload JSON crudo) · Caddy (TLS).
Datos 100 % ficticios. No usar en producción sin revisar `.env`, HTTPS y contraseñas.

## Arranque con Docker (MariaDB + MongoDB reales)
```bash
cp .env.example .env            # completa DB_PASSWORD, DB_ROOT_PASSWORD y DJANGO_SECRET_KEY (y DB_ENGINE=mysql)
docker compose up --build -d
docker compose exec web python manage.py seed_demo      # imprime usuarios demo y el token de la API
```
Abre http://localhost:8000 (en producción define `DJANGO_DEBUG=0` y sirve tras HTTPS).

## Arranque local rápido (sin servidores de BD) – Windows, Linux y macOS
Por defecto el proyecto usa SQLite y un MongoDB simulado en memoria; no hace falta instalar MariaDB ni MongoDB.
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell). En Linux/macOS: . .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo         # imprime usuarios demo y el token de la API (guárdalos)
python manage.py runserver
```
Los payloads JSON del modo simulado viven solo en la memoria del servidor. Para usar MariaDB y MongoDB reales: `DB_ENGINE=mysql`, `MONGO_URI=mongodb://...` (o Docker, arriba).

## Recuperar contraseña
- Autoservicio: en `/login/` → «¿Olvidaste tu contraseña?» → correo con enlace (vigencia 1 h, un solo uso) → nueva clave con la política de 12+ caracteres.
- Administrado: en *Usuarios* el Administrador pulsa «Enviar enlace de clave» (nunca ve ni fija la clave).
- En desarrollo el correo **se imprime en la consola donde corre `runserver`**; copia el enlace desde ahí. Para SMTP real: `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS=1`.
- La respuesta es idéntica exista o no el correo; máx. 5 solicitudes/hora por IP; un reset exitoso levanta el bloqueo por intentos fallidos. Todo queda en auditoría (`PASSWORD_RESET_*`).

## Simulador de la cámara (CU04)
```bash
python simulador/camara.py --url http://127.0.0.1:8000 --token <TOKEN> --n 5 --demo-errores
```
Muestra 201, 409 (duplicado), 422 (incompleto) y 401 (token inválido).

## Roles y casos de uso
| Caso de uso | Administrador | Supervisor | Operador | Ruta |
|---|:-:|:-:|:-:|---|
| CU01 Autenticar (bloqueo 15 min tras 5 fallos) | ● | ● | ● | /login/ |
| CU02 Usuarios y permisos | ● | | | /administracion/usuarios/ |
| CU03 Lotes y batches | ● | | | /administracion/lotes/ |
| CU04/04a API de recepción + alarmas | sistema externo | | | POST /api/v1/inspecciones/ |
| CU05 Trazabilidad | ● | ● | ● | /trazabilidad/ |
| CU06 Historial con filtros | ● | ● | ● | /historial/ |
| CU07/07a Dashboard, por turno y receta | ● | ● | ● | / |
| CU08 Observaciones (anti-XSS) | | ● | ● | /inspecciones/<id>/ |
| CU09 Recetas | ● | | | /administracion/recetas/ |
| CU10 Detalle de inspección | ● | ● | ● | /inspecciones/<id>/ |
| CU11 Alarmas y reconocimiento | | ● | ● | /alarmas/ |
| CU12 Bitácora de auditoría | ● | | | /administracion/auditoria/ |
| CU13 Exportar CSV (neutraliza fórmulas) | | ● | | /historial/exportar/ |
| CU14 Recuperar contraseña | ● | ● | ● | /password/recuperar/ |
| Informe de gestión (filtros, gráficos, PDF) | ● | ● | | /informe-gestion/ |

## Pruebas
```bash
pytest -v                                                  # 89 pruebas (SQLite + mongomock; 1 se omite: requiere MariaDB)
DB_ENGINE=mysql DB_USER=... DB_PASSWORD=... pytest -v      # contra MariaDB real: 89 pruebas pasan
pytest --cov=trazabilidad --cov-report=term                # cobertura (93 % en la última ejecución)
```
Detalle, carga (Locust), Bandit, pip-audit y respaldo en `docs/PRUEBAS.md`; resultados en `evidencias/`.

## Notas de diseño
- Orden de escritura: transacción en MariaDB → confirmación → `upsert` en MongoDB. Un `id_externo` repetido responde 409 y completa MongoDB si faltaba; si Mongo falla, la inspección se conserva y `reconciliar_mongo` la repara (ver `docs/ARQUITECTURA.md`).
- `estado_original` nunca se recalcula; se guarda un snapshot `limite_min/limite_max` de la receta.
- La inmutabilidad de inspecciones y la bitácora append-only se aplican en el modelo **y** con *triggers* de la base de datos (migración `0002`).
- Cuentas: la baja es lógica (`is_active`) y el historial se conserva.

## Estructura
```
aza/            configuración (settings, settings_test)
trazabilidad/   app: modelos, servicios, API, vistas, plantillas, pruebas, comandos
deploy/         Caddy, entrypoint, respaldo/restauración, humo, aprovisionamiento
docs/           ARQUITECTURA, DESPLIEGUE, PRUEBAS
loadtest/       locustfile.py          simulador/  camara.py
evidencias/     logs y resultados reales de pruebas, carga, seguridad y respaldo
```
Ver también `CONTRIBUTING.md` (flujo Git/Kanban) y `docs/DESPLIEGUE.md` (producción con Docker y Caddy).
