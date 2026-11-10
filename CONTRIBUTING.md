# Flujo de trabajo

Proyecto individual. Se sigue igualmente un flujo profesional para que el historial sea trazable.

* **Ramas**: `main` siempre estable; una rama por actividad del cronograma: `feat/A08-api-recepcion`, `fix/...`, `docs/...`.
* **Commits** (Conventional Commits): `feat:`, `fix:`, `test:`, `docs:`, `chore:`; en español, en imperativo, referenciando la actividad (`A08`) o el requisito (`RF-12`).
* **Kanban**: límite de 2 tareas en curso. Una tarea pasa a *Hecho* solo con prueba pasando y documentación actualizada.
* **Revisión**: antes de integrar a `main` se ejecuta `pytest`, `bandit` y `pip-audit` (también en CI, ver `.github/workflows/ci.yml`).
* **Estándares**: PEP 8, funciones cortas, sin secretos en el repositorio, migraciones versionadas.
