# Despliegue en producción — Torio

Guía para desplegar el backend Torio (Django 5.2 multi-tenant) en un servidor
Linux con **PostgreSQL + Gunicorn + Nginx + systemd**.

> No hay Docker todavía (ver _Pendiente_ en el `README.md`). Esta guía cubre el
> despliegue tradicional sobre una VM Ubuntu/Debian.

---

## 1. Arquitectura del despliegue

```
              HTTPS                      proxy_pass               socket
  Cliente  ─────────►  Nginx  ───────────────────────────►  Gunicorn  ──►  Django (torioapp.wsgi)
 (frontend)          (TLS, estáticos)   X-Tenant + headers   (systemd)         │
                                                                  red privada   │
                                                  ┌───────────────────────────┘ │
                                                  ▼                             ▼
                                     PostgreSQL gestionado            Backblaze B2 (archivos)
                                    (servicio externo, schema
                                          por tenant)
```

> **La base de datos es un servicio externo/gestionado** (PostgreSQL administrado:
> RDS, Cloud SQL, Supabase, instancia dedicada, etc.). El servidor de la app **no
> corre PostgreSQL**: solo se conecta a él por red. No se instala ni administra el
> motor en esta VM.

Puntos clave específicos de este proyecto:

- **Settings de producción ya cableados.** `torioapp/wsgi.py` y `asgi.py` hacen
  `setdefault('DJANGO_SETTINGS_MODULE', 'torioapp.settings.prod')`. Aun así, lo
  fijamos explícitamente en el servicio systemd.
- **Multi-tenancy por header `X-Tenant`** (`seguridad.middleware.TenantHeaderMiddleware`,
  primero en `MIDDLEWARE`):
  - Sin header (o con el nombre del schema público) → opera en el **schema público**
    (autenticación, registro de tenants, admin).
  - Con header válido → ese tenant. Header inválido → 404.
  - **Implicación:** un único host de backend sirve a todos los tenants. **No**
    se necesitan subdominios comodín para resolver el tenant; el frontend envía
    `X-Tenant: <schema>` en cada petición. Nginx solo debe **pasar los headers**
    (comportamiento por defecto; no los filtres).
- **Archivos** (imágenes, adjuntos) se guardan en **Backblaze B2** vía `boto3`
  (`utilidades/backblaze.py`), no en disco local. No hay que servir `MEDIA` desde Nginx.
- **Estáticos** se sirven desde Nginx (`STATIC_ROOT = staticfiles/`).
- **HTTPS lo termina Nginx.** `prod.py` ya define
  `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`, así que Nginx
  debe enviar `X-Forwarded-Proto`.

---

## 2. Requisitos del servidor

- Ubuntu 22.04+ / Debian 12+ (o equivalente)
- Python 3.12+
- **Acceso de red a un PostgreSQL 14+ gestionado/externo** (no se instala aquí)
- Nginx
- Un usuario de sistema sin privilegios para correr la app (ej. `torio`)
- Certificado TLS (recomendado: Let's Encrypt / certbot)

```bash
sudo apt update
# Solo el cliente de PostgreSQL (psql, pg_dump) para administración/backups remotos.
# NO se instala el servidor: la BD es un servicio externo.
sudo apt install -y python3.12 python3.12-venv python3-pip \
    postgresql-client nginx git
```

> `psycopg2-binary` (en `requirements.txt`) trae su propia copia de libpq, así que
> no hace falta `libpq-dev` ni compilar nada.

---

## 3. Base de datos PostgreSQL (servicio externo/gestionado)

La BD vive en **otro servicio** (PostgreSQL administrado o instancia dedicada). En
el servidor de la app no se instala ni corre el motor; solo se conecta por red.

Provisiona en el servicio gestionado (vía su consola, o `psql` apuntando al host
remoto). `django-tenants` exige que el rol de la app pueda **crear schemas** (cada
tenant es un schema creado en caliente con `auto_create_schema=True`):

```bash
# Ejecutar contra el host gestionado con un usuario administrador del servicio.
psql "host=db.tu-proveedor.com port=5432 user=admin dbname=postgres" <<'SQL'
CREATE USER torio WITH PASSWORD 'CLAVE_FUERTE_AQUI';
CREATE DATABASE bdtorio OWNER torio;
-- El owner de la BD ya puede crear schemas; si usas otro rol, otorga:
-- GRANT CREATE ON DATABASE bdtorio TO torio;
SQL
```

Requisitos del servicio gestionado:

- **Conectividad de red** desde la VM de la app hacia el puerto de la BD
  (security group / firewall / VPC peering / IP allowlist según el proveedor).
- El rol `torio` con privilegio de **crear schemas** (para el alta de tenants).
- **TLS recomendado.** Si el proveedor exige conexión cifrada, añade `OPTIONS` al
  bloque `DATABASES['default']` en `torioapp/settings/base.py` (no es configurable
  por `.env` actualmente):

  ```python
  'OPTIONS': {'sslmode': 'require'},   # o 'verify-full' con 'sslrootcert'
  ```

> El backend de BD es `django_tenants.postgresql_backend` (ya configurado en
> `base.py`). No cambiar el `ENGINE`.

---

## 4. Código y entorno virtual

```bash
# Como usuario de la app
sudo useradd --system --create-home --shell /bin/bash torio
sudo su - torio

git clone <repo> /home/torio/torio
cd /home/torio/torio

python3.12 -m venv /home/torio/venv
source /home/torio/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`gunicorn` ya está en `requirements.txt`, así que no hay que instalarlo aparte.

---

## 5. Variables de entorno (`.env` de producción)

El proyecto lee la configuración con `python-decouple` desde un archivo `.env`
en la raíz. **`.env` está en `.gitignore`** — créalo en el servidor con valores reales.

```ini
# ── Núcleo ─────────────────────────────────────────────
ENV=prod
DEBUG=False
SECRET_KEY=<generar con: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
# Host(s) del backend. Sin comodín de subdominio porque el tenant va por header.
ALLOWED_HOSTS=api.tu-dominio.com

# ── Base de datos (servicio externo/gestionado) ────────
DATABASE_NAME=bdtorio
DATABASE_USER=torio
DATABASE_CLAVE=CLAVE_FUERTE_AQUI
DATABASE_HOST=db.tu-proveedor.com     # host del PostgreSQL gestionado (no localhost)
DATABASE_PORT=5432

# ── Logging ────────────────────────────────────────────
LOG_LEVEL=INFO
DJANGO_LOG_LEVEL=INFO

# ── URLs y cookies ─────────────────────────────────────
BACKEND_URL=https://api.tu-dominio.com
FRONTEND_URL=https://app.tu-dominio.com
FRONTEND_CUENTA_URL=https://app.tu-dominio.com
ZINC_URL=https://zinc.tu-dominio.com
TENANT_BASE_DOMAIN=tu-dominio.com
# Punto inicial para compartir cookie JWT entre subdominios del frontend.
AUTH_COOKIE_DOMAIN=.tu-dominio.com
AUTH_COOKIE_SECURE=True

# ── Seguridad / prod (leídas por settings/prod.py) ─────
CORS_ALLOWED_ORIGINS=https://app.tu-dominio.com,https://www.tu-dominio.com
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000

# ── Docs API: NO en producción ─────────────────────────
ENABLE_API_DOCS=False

# ── Sentry (control de errores) ────────────────────────
SENTRY_DSN=https://<clave>@<org>.ingest.sentry.io/<proyecto>
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=                       # opcional: SHA de git del despliegue
SENTRY_TRACES_SAMPLE_RATE=0.0         # 0.0 = solo errores; subir si se quiere APM
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_PII=False                 # no enviar cookies/headers/usuario

# ── Cloudflare Turnstile ───────────────────────────────
TURNSTILE_ENABLED=True
TURNSTILE_SECRET_KEY=<secret real>

# ── Wompi (pagos) ──────────────────────────────────────
WOMPI_EVENTS_SECRET=<secret real>
WOMPI_INTEGRITY_SECRET=<secret real>

# ── Backblaze B2 (almacenamiento de archivos) ──────────
B2_KEY_ID=<key id de producción>
B2_APP_KEY=<app key de producción>
B2_ENDPOINT_URL=https://s3.us-east-005.backblazeb2.com
B2_BUCKET_PUBLICO=torio-publico-prod
B2_BUCKET_PRIVADO=torio-privado-prod
B2_CDN_URL_PUBLICO=https://torio-publico-prod.s3.us-east-005.backblazeb2.com
```

Protege el archivo:

```bash
chmod 600 /home/torio/torio/.env
```

> **Importante:** usa buckets B2 y credenciales **de producción** distintos a los
> de desarrollo (los del `.env` de dev apuntan a `*-desarrollo`).

---

## 6. Migraciones y datos iniciales

`django-tenants` separa migraciones del schema público y de los tenants.

```bash
cd /home/torio/torio
source /home/torio/venv/bin/activate
export DJANGO_SETTINGS_MODULE=torioapp.settings.prod

# 1. Migrar el schema público (apps compartidas)
python manage.py migrate_schemas --shared

# 2. Crear el tenant público (una sola vez, primera instalación)
python manage.py shell <<'PY'
from contenedor.models import CtnCliente, CtnDominio
tenant = CtnCliente(schema_name='public', nombre='Public')
tenant.save(verbosity=1)
CtnDominio.objects.get_or_create(domain='api.tu-dominio.com', tenant=tenant,
                                 defaults={'is_primary': True})
PY

# 3. Migrar todos los tenants existentes
python manage.py migrate_schemas

# 4. Datos de referencia del schema público (idempotente)
python manage.py cargar_geodata

# 5. Datos de referencia de los tenants (idempotente)
python manage.py cargar_datos_tenant

# 6. Superusuario para el admin (schema público)
python manage.py createsuperuser
```

> En cada **redeploy** que incluya migraciones, ejecutar `migrate_schemas --shared`
> y luego `migrate_schemas` (ver §10).

---

## 7. Archivos estáticos

```bash
python manage.py collectstatic --noinput
```

Genera `staticfiles/`, servido por Nginx (ver §9). Repetir en cada release que
cambie estáticos (el admin de Django, Swagger si se habilitara, etc.).

---

## 8. Gunicorn como servicio systemd

Crear `/etc/systemd/system/torio.service`:

```ini
[Unit]
Description=Torio Gunicorn (Django)
# La BD es externa: solo dependemos de la red, no de un postgresql local.
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=torio
Group=torio
WorkingDirectory=/home/torio/torio
Environment=DJANGO_SETTINGS_MODULE=torioapp.settings.prod
ExecStart=/home/torio/venv/bin/gunicorn torioapp.wsgi:application \
    --workers 3 \
    --bind unix:/run/torio/gunicorn.sock \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=3
RuntimeDirectory=torio
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
```

Notas:
- **Workers:** regla práctica `(2 × núcleos) + 1`. Ajusta a la VM.
- `RuntimeDirectory=torio` crea `/run/torio` (donde vive el socket) con los permisos
  correctos en cada arranque.
- `--timeout 60` da margen a operaciones pesadas (importar Excel, generar PDFs).

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now torio
sudo systemctl status torio
```

---

## 9. Nginx como reverse proxy

Crear `/etc/nginx/sites-available/torio`:

```nginx
upstream torio_app {
    server unix:/run/torio/gunicorn.sock;
}

server {
    listen 80;
    server_name api.tu-dominio.com;
    # Redirección a HTTPS la maneja certbot o este bloque:
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.tu-dominio.com;

    ssl_certificate     /etc/letsencrypt/live/api.tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.tu-dominio.com/privkey.pem;

    client_max_body_size 6M;   # importar Excel: límite del backend es 5 MB

    # Estáticos servidos directo por Nginx
    location /static/ {
        alias /home/torio/torio/staticfiles/;
        expires 30d;
        access_log off;
    }

    location / {
        proxy_pass http://torio_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # requerido por SECURE_PROXY_SSL_HEADER
        # X-Tenant y Authorization se reenvían tal cual (Nginx no los filtra).
        proxy_redirect off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/torio /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

TLS con Let's Encrypt:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.tu-dominio.com
```

> El `client_max_body_size` debe ser ≥ al límite de importación del backend (5 MB,
> definido en `ImportarExcelMixin.MAX_TAMANO_ARCHIVO_BYTES`). 6 MB deja margen.

---

## 10. Actualizaciones (redeploy)

```bash
sudo su - torio
cd /home/torio/torio
source /home/torio/venv/bin/activate
export DJANGO_SETTINGS_MODULE=torioapp.settings.prod

git pull
pip install -r requirements.txt          # si cambiaron dependencias

python manage.py migrate_schemas --shared
python manage.py migrate_schemas         # tenants
python manage.py cargar_geodata          # si cambiaron fixtures públicos
python manage.py cargar_datos_tenant     # si cambiaron fixtures de tenant
python manage.py collectstatic --noinput

exit
sudo systemctl restart torio
```

> Para un cero-downtime básico, `sudo systemctl reload torio` (HUP) reinicia los
> workers sin cortar conexiones nuevas. Tras migraciones incompatibles, prefiere
> `restart`.

---

## 11. Checklist de seguridad pre-producción

```bash
export DJANGO_SETTINGS_MODULE=torioapp.settings.prod
python manage.py check --deploy
```

`settings/prod.py` ya aplica: `DEBUG=False`, `SECURE_SSL_REDIRECT`,
`SESSION/CSRF_COOKIE_SECURE`, HSTS (1 año, subdominios, preload),
`SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY`.

Verifica además:

- [ ] `SECRET_KEY` única y secreta (no la de dev).
- [ ] `DEBUG=False` y `ENABLE_API_DOCS=False`.
- [ ] `ALLOWED_HOSTS` con el host real del backend.
- [ ] `CORS_ALLOWED_ORIGINS` solo con los orígenes del frontend de prod.
- [ ] `AUTH_COOKIE_SECURE=True` y `AUTH_COOKIE_DOMAIN` con punto inicial.
- [ ] Credenciales y buckets B2 **de producción** (no `*-desarrollo`).
- [ ] `.env` con `chmod 600` y fuera de git.
- [ ] Conectividad de red a la BD gestionada abierta solo desde la VM de la app
      (allowlist/security group), y TLS exigido si el proveedor lo soporta.
- [ ] Rol PostgreSQL con privilegio de crear schemas (alta de tenants).
- [ ] Backups automáticos del servicio de BD gestionado activados (§13).
- [ ] Turnstile y Wompi con secrets reales.
- [ ] `SENTRY_DSN` configurado y `SENTRY_SEND_PII=False` (ver §12 › Sentry).
- [ ] Backups de PostgreSQL programados (ver §13).

---

## 12. Operación

```bash
# Logs de la app (stdout/stderr de Gunicorn → journald)
sudo journalctl -u torio -f

# Estado / reinicio
sudo systemctl status torio
sudo systemctl restart torio
sudo systemctl reload torio          # recarga suave (HUP)

# Logs de Nginx
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### Sentry (control de errores)

La app reporta excepciones a **Sentry** automáticamente cuando `SENTRY_DSN` está
definido (integración Django auto-activada en `torioapp/settings/base.py`).

- **Activación:** basta con setear `SENTRY_DSN` en el `.env` (§5). Sin DSN, queda
  desactivado — por eso en dev no envía nada.
- **Tenant por evento:** cada error se etiqueta con `tenant=<schema>`
  (`TenantHeaderMiddleware`), así se filtra/segmenta por cliente en Sentry.
- **Privacidad:** `SENTRY_SEND_PII=False` por defecto → no se envían cookies (JWT),
  headers de auth ni datos de usuario.
- **Performance/APM:** desactivado por defecto (`SENTRY_TRACES_SAMPLE_RATE=0.0`).
  Subir gradualmente (ej. `0.1`) si se quiere tracing.
- **Releases:** setear `SENTRY_RELEASE` al SHA de git del despliegue asocia los
  errores a cada versión (útil para detectar regresiones tras un deploy).

Verificar la integración tras el despliegue (envía un evento de prueba):

```bash
source /home/torio/venv/bin/activate
export DJANGO_SETTINGS_MODULE=torioapp.settings.prod
python -c "import sentry_sdk; sentry_sdk.capture_message('Despliegue Torio OK')"
# Debe aparecer en el dashboard de Sentry en segundos.
```

---

## 13. Backups

El servicio de BD gestionado normalmente ya ofrece **backups automáticos y
point-in-time recovery** — actívalos y define la retención en la consola del
proveedor. Eso debe ser la línea base.

Como respaldo adicional/portátil, un dump lógico desde la VM (o cualquier máquina
con acceso) cubre **todos los schemas** (público + tenants) en un solo archivo:

```bash
# Backup completo (todos los tenants), apuntando al host gestionado
pg_dump "host=db.tu-proveedor.com port=5432 user=torio dbname=bdtorio" \
    -Fc > /var/backups/bdtorio_$(date +%F).dump

# Restore
pg_restore "host=db.tu-proveedor.com port=5432 user=torio dbname=bdtorio" \
    --clean /var/backups/bdtorio_AAAA-MM-DD.dump
```

Programar con cron (ej. diario). Los archivos en B2 se respaldan según la política
de versionado/retención del bucket en Backblaze.

---

## 14. Alta de un nuevo tenant (en producción)

```bash
python manage.py shell <<'PY'
from contenedor.models import CtnCliente, CtnDominio
cliente = CtnCliente.objects.create(schema_name='acme', nombre='ACME S.A.')
CtnDominio.objects.create(domain='acme.tu-dominio.com', tenant=cliente, is_primary=True)
PY

# Sembrar datos de referencia del tenant recién creado
python manage.py cargar_datos_tenant --schema acme
```

El schema PostgreSQL se crea automáticamente (`auto_create_schema=True`). El
`schema_name` debe ser único, empezar por letra minúscula y contener solo letras,
dígitos y guion bajo. El frontend luego envía `X-Tenant: acme` en sus peticiones.

---

## Resumen rápido (orden de ejecución, primera instalación)

1. Instalar paquetes del sistema (cliente PostgreSQL, sin servidor) (§2)
2. Aprovisionar rol/BD en el PostgreSQL gestionado + abrir conectividad (§3)
3. Clonar código + venv + `pip install` (§4)
4. Crear `.env` de producción (§5)
5. `migrate_schemas --shared` → crear tenant público → `migrate_schemas` (§6)
6. `cargar_geodata` + `cargar_datos_tenant` + `createsuperuser` (§6)
7. `collectstatic` (§7)
8. systemd `torio.service` + `enable --now` (§8)
9. Nginx + TLS (§9)
10. `check --deploy` (§11)
