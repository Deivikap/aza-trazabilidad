# Arquitectura de la solución

## Componentes
| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Presentación | Plantillas Django + Bootstrap 5.3 (sin estilos ni scripts en línea; CSP estricta) | Dashboard, historial, trazabilidad, alarmas, administración |
| Integración | Django REST Framework (`POST /api/v1/inspecciones/`, token Bearer con hash SHA-256) | Recepción desde la cámara/sistema de inspección |
| Lógica de negocio | `trazabilidad/services.py` | Validación, idempotencia, persistencia dual, alarmas |
| Persistencia relacional | MariaDB 11.4 (fuente de verdad) | Perfiles, usuarios, recetas, lotes, batches, inspecciones, observaciones, alarmas, auditoría |
| Persistencia documental | MongoDB 7.0 (`mensajes_inspeccion`) | Payload JSON crudo e inmutable de cada inspección |
| Borde | Caddy (TLS automático, HSTS, límite de cuerpo 1 MB) | Único servicio expuesto (80/443) |

Contratos internos: las vistas web y la API solo llaman a `services.procesar()` (ingesta) y a consultas del ORM; no escriben en MongoDB directamente. Solo `mongo.py` conoce a `pymongo`.

## Orden de escritura y recuperación (CU04)
1. Autenticar el token y aplicar límite de tasa (60/min por token) → 401 / 429.
2. Validar esquema, tipos, rangos y fecha → 400 / 422 (queda auditado como `INGESTA_RECHAZADA`).
3. Verificar que lote, batch y receta existan y sean coherentes → 422.
4. `transaction.atomic()` en **MariaDB**: inserta `Inspeccion` (con copia de `limite_min/limite_max`) y el evento `INGESTA_OK`. La restricción `UNIQUE(id_externo)` decide la idempotencia: el duplicado responde **409** sin crear otra fila.
5. Tras confirmar MariaDB, `upsert` del payload en MongoDB. Si Mongo falla, la inspección **no se pierde**: se audita `MONGO_FALLO` y `manage.py reconciliar_mongo --reparar` rehace el documento desde la fila relacional.
6. Si la solicitud es un duplicado y Mongo no tenía el documento, se completa antes de responder 409.
7. Se evalúan alarmas (`SIN_RECETA`, rechazos consecutivos) y se auditan.

Solicitudes concurrentes: ocho envíos simultáneos del mismo `id_externo` terminan con un único 201 y siete 409 (prueba `test_concurrencia_mismo_id_externo_un_solo_201`, ejecutada contra MariaDB).

## ¿Por qué dos motores?
* **MariaDB**: integridad transaccional (ACID), claves foráneas `ON DELETE RESTRICT`, `UNIQUE`, índices y *triggers* que impiden modificar o borrar el resultado original y la bitácora. La trazabilidad lote → batch → receta → inspección es una consulta relacional con joins.
* **MongoDB**: conserva el mensaje JSON tal como lo emitió el sistema de inspección. El esquema es flexible, de modo que si la cámara agrega campos no hay que migrar tablas, y sirve de evidencia forense del mensaje original.
* **Limitaciones asumidas**: dos motores implican más operación (respaldos, parches, credenciales) y no existe una transacción distribuida, por lo que la consistencia entre ambos es eventual. Se mitiga con el orden de escritura, `MONGO_FALLO` en auditoría y `reconciliar_mongo`.
* **Alternativa descartada**: una columna JSON en MariaDB bastaría a esta escala y simplificaría la operación. Se mantiene MongoDB para separar el dato normalizado del mensaje crudo y porque el desafío pide evidenciar ambos tipos de datos. Es una decisión revisable si la empresa prefiere un único motor.

## Segmentación de red (producción)
`docker-compose.prod.yml` define dos redes: `edge` (Caddy y web) y `data` (`internal: true`, MariaDB, MongoDB y web). Las bases de datos no publican puertos ni tienen salida a Internet. El contenedor web corre sin privilegios (`cap_drop: ALL`, `read_only`, `no-new-privileges`).

## Seguridad aplicada
Argon2 para contraseñas (mín. 12), bloqueo de 15 min tras 5 fallos (django-axes), RBAC por grupos, CSRF, CSP sin `unsafe-inline`, cookies `Secure/HttpOnly/SameSite`, anti-enumeración en recuperación de clave, exportación CSV que neutraliza fórmulas, respuestas de error sin detalles internos y auditoría append-only reforzada con *triggers* en el motor.
