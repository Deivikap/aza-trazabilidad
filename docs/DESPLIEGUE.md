# Guía de despliegue y operación

## 0. Requisitos
VM Linux (Ubuntu 24.04), 2 vCPU y 4 GB de RAM como mínimo, puertos 80/443 abiertos y un dominio (o `<IP>.sslip.io`).

## 1. Preparar la VM
```bash
sudo bash deploy/provision_ubuntu.sh     # Docker, firewall (22/80/443), fail2ban, parches automáticos
```
## 2. Configurar secretos
```bash
cp .env.prod.example .env.prod && chmod 600 .env.prod
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # úsalo en DJANGO_SECRET_KEY
```
Completa `DOMAIN`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DB_PASSWORD`, `DB_ROOT_PASSWORD`, `MONGO_PASSWORD` y `BACKUP_PASSPHRASE`. `.env.prod` nunca se sube al repositorio.

## 3. Levantar
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py crear_usuario jperez --rol ADMIN --email jperez@aza.cl
```
El `entrypoint.sh` espera a MariaDB, aplica migraciones (incluye los *triggers* de inmutabilidad), crea la tabla de caché y recolecta estáticos.

## 4. Verificar
```bash
bash deploy/smoke_test.sh https://<DOMINIO> <TOKEN_API>   # salud, HTTPS, cabeceras, login y API 401/422/201/409
```
El token de la API se genera con `python manage.py shell` (`ApiToken.crear("camara-planta")`) y se muestra una sola vez.

## 5. Respaldos y restauración
```bash
crontab -e   # 0 2 * * *  cd /opt/aza && bash deploy/backup.sh >> /var/log/aza_backup.log 2>&1
bash deploy/restore.sh /var/backups/aza/aza-AAAAMMDD-HHMMSS.tar.enc
```
Los respaldos se cifran con AES-256-CBC (PBKDF2, 200 000 iteraciones), llevan suma SHA-256 y se conservan 14. Copia el `.enc` fuera de la VM. Tras restaurar se ejecuta `reconciliar_mongo`. Para validar el ciclo de MariaDB sin Docker: `bash deploy/prueba_respaldo_mariadb.sh`.

## 6. Actualizar
`git pull && docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` (las migraciones corren solas). Antes de actualizar, ejecuta un respaldo.

## 7. Operación
| Tarea | Frecuencia | Cómo |
|---|---|---|
| Respaldo | diaria | cron + `deploy/backup.sh` |
| Prueba de restauración | mensual | `deploy/restore.sh` en una VM de prueba |
| Parches del SO y de la imagen | semanal | `unattended-upgrades` y reconstruir la imagen |
| Revisar dependencias | mensual | `pip-audit -r requirements.txt` |
| Revisar bitácora y alarmas | diaria | pantallas Auditoría y Alarmas |
| Conciliación MariaDB/Mongo | semanal | `manage.py reconciliar_mongo` |
