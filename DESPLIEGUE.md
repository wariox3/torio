# Despliegue en producción — Torio

Guía para desplegar el backend Torio (Django 5.2 multi-tenant) en un servidor
Linux con **PostgreSQL + Gunicorn + Nginx + systemd**.

> No hay Docker todavía (ver _Pendiente_ en el `README.md`). Esta guía cubre el
> despliegue tradicional sobre una VM Ubuntu 24.04 (ver §2).

---

## 1. Arquitectura del despliegue

```
              HTTPS                      proxy_pass          127.0.0.1:8060
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

### Convención de rutas (FHS)

La aplicación se despliega bajo **`/opt/torio`** (software de aplicación
autocontenido, según el FHS — **no** en `/home`, que es para usuarios humanos):

```
/opt/torio/              # checkout de git (manage.py, requirements.txt, ...)
├── .env                 # configuración de producción (chmod 600, ignorado por git)
├── venv/                # entorno virtual (ignorado por git)
└── staticfiles/         # salida de collectstatic (ignorado por git)
```

`venv/`, `staticfiles/` y `.env` están en `.gitignore`, así que conviven con el
checkout sin ensuciar `git status` ni estorbar el `git pull` de las actualizaciones (§10).

Corre como un **usuario de sistema sin login** (`torio`), compatible con el
endurecimiento de systemd (`ProtectHome=true`). Su home es `/var/lib/torio`, **no**
`/opt/torio`: ahí caen cachés como la de pip (`.cache/`), que dentro del checkout
aparecerían como archivos sin versionar. El `.env` vive en `/opt/torio/.env` (donde
`python-decouple` lo busca) con permisos `600`.

---

## 2. Requisitos del servidor

- **Ubuntu 24.04 LTS** (recomendado: es el que trae Python 3.12 en sus repositorios)
- Python 3.12 (el proyecto se desarrolla y prueba con 3.12)
- **Acceso de red a un PostgreSQL 14+ gestionado/externo** (no se instala aquí)
- Nginx
- Un usuario de sistema sin privilegios para correr la app (ej. `torio`)
- Certificado TLS (recomendado: Let's Encrypt / certbot)

> **Otras distribuciones:** Ubuntu 22.04 trae Python 3.10 y Debian 12 trae 3.11, así
> que en ellas `apt install python3.12` falla. En Ubuntu 22.04 se puede instalar desde
> el PPA `deadsnakes`; en Debian 12 no hay paquete oficial. Si no hay una razón para
> usar otra, parte de Ubuntu 24.04.

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip nginx git
```

**Cliente de PostgreSQL (`psql`, `pg_dump`).** NO se instala el servidor: la BD es un
servicio externo. Pero `pg_dump` **debe ser de la misma versión mayor que el servidor o
más nueva**: uno más viejo se niega a volcar (`server version mismatch`), y el
`postgresql-client` de los repositorios de Ubuntu es el de la distribución (16 en
24.04), no el del servicio gestionado. Instálalo desde el repositorio oficial (PGDG)
con la versión del servidor:

```bash
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
# Reemplaza 16 por la versión mayor del servidor gestionado (SELECT version();)
sudo apt install -y postgresql-client-16
pg_dump --version
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
# Usuario de sistema sin login (no interactivo). Home en /var/lib/torio, fuera del
# checkout, para que las cachés (pip) no queden dentro del repo.
sudo useradd --system --create-home --home-dir /var/lib/torio \
    --shell /usr/sbin/nologin torio

# /opt/torio debe existir VACÍO: git clone solo acepta un directorio vacío.
sudo mkdir -p /opt/torio
sudo chown torio:torio /opt/torio

# Clonar y crear el venv como el usuario de servicio (sin shell de login).
# El repo es público: el clone y el `git pull` de las actualizaciones (§10) no piden credenciales.
sudo -u torio git clone https://github.com/wariox3/torio.git /opt/torio
sudo -u torio python3.12 -m venv /opt/torio/venv
sudo -u torio /opt/torio/venv/bin/pip install --upgrade pip
sudo -u torio /opt/torio/venv/bin/pip install -r /opt/torio/requirements.txt
```

- `gunicorn` ya está en `requirements.txt`, no se instala aparte.
- Como el usuario `torio` no tiene shell de login, los comandos de administración
  se ejecutan con `sudo -u torio <ruta-venv>/python ...` (ver §6) o desde una
  shell puntual: `sudo -u torio -s`.
- El árbol `/opt/torio` queda propiedad de `torio`; el servicio solo lee
  (escribe únicamente en `collectstatic`, ejecutado en el despliegue).

---

## 5. Variables de entorno (`.env` de producción)

El proyecto lee la configuración con `python-decouple` desde un archivo `.env`
en la raíz del código (`/opt/torio/.env`). **`.env` está en `.gitignore`** —
créalo en el servidor con valores reales.

> ⚠️ **`python-decouple` NO soporta comentarios en la misma línea del valor.**
> Todo lo que esté a la derecha del `=` se toma como valor. Los comentarios deben
> ir en su propia línea empezando con `#`. Es decir, `CLAVE=0.0  # nota` rompe el
> arranque (`could not convert string to float`); usa la nota en la línea de arriba.

```ini
# ── Núcleo ─────────────────────────────────────────────
ENV=prod
DEBUG=False
SECRET_KEY=<generar con: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
# Host(s) del backend. Sin comodín de subdominio porque el tenant va por header.
ALLOWED_HOSTS=reddocapi2.co

# ── Base de datos (servicio externo/gestionado) ────────
DATABASE_NAME=bdtorio
DATABASE_USER=torio
DATABASE_CLAVE=CLAVE_FUERTE_AQUI
# host del PostgreSQL gestionado (no localhost)
DATABASE_HOST=db.tu-proveedor.com
DATABASE_PORT=5432

# ── Logging ────────────────────────────────────────────
LOG_LEVEL=INFO
DJANGO_LOG_LEVEL=INFO

# ── URLs y cookies ─────────────────────────────────────
BACKEND_URL=https://reddocapi2.co
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
# True porque Nginx va adelante y reescribe X-Forwarded-For (ver §9). Sin esto, la
# bitácora de accesos y los desafíos MFA registran la IP de Nginx (127.0.0.1).
CONFIAR_EN_PROXY=True

# ── MFA (obligatoria) ──────────────────────────────────
# Clave Fernet propia, distinta de SECRET_KEY. Sin ella, todo uso del segundo factor
# falla con ImproperlyConfigured. Generar con:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# NO rotarla sin migrar los secretos: los TOTP ya configurados dejan de descifrarse.
MFA_ENCRYPTION_KEY=<clave fernet>
# Opcional: tope absoluto de la sesión en días (default 30)
SESION_MAXIMA_DIAS=30

# ── Docs API: NO en producción ─────────────────────────
ENABLE_API_DOCS=False

# ── Sentry (control de errores) ────────────────────────
SENTRY_DSN=https://<clave>@<org>.ingest.sentry.io/<proyecto>
SENTRY_ENVIRONMENT=production
# Opcional: SHA de git del despliegue
SENTRY_RELEASE=
# Muestreo de performance: 0.0 = solo errores; subir si se quiere APM
SENTRY_TRACES_SAMPLE_RATE=0.0
SENTRY_PROFILES_SAMPLE_RATE=0.0
# No enviar cookies/headers/usuario
SENTRY_SEND_PII=False

# ── Cloudflare Turnstile ───────────────────────────────
TURNSTILE_ENABLED=True
TURNSTILE_SECRET_KEY=<secret real>

# ── Wompi (pagos) ──────────────────────────────────────
WOMPI_INTEGRITY_SECRET=<secret real>

# ── RedEDoc (servicio Nobelio) ─────────────────────────
REDEDOC_URL=https://api.rededoc.uk
REDEDOC_KEY=<llave real>
REDEDOC_WEBHOOK_SECRETO=<secreto compartido con rededoc>

# ── Backblaze B2 (almacenamiento de archivos) ──────────
# Cada bucket tiene su propia application key, restringida a él: no son
# intercambiables. Usar la del privado contra el público no da un 403, B2 corta la
# conexión y el error parece de red.
B2_ENDPOINT_URL=https://s3.us-east-005.backblazeb2.com
# Bucket privado
B2_KEY_ID=<key id del bucket privado>
B2_APP_KEY=<app key del bucket privado>
B2_BUCKET_PRIVADO=torio-privado-prod
# Bucket "público" (pese al nombre, sin lectura pública: solo lo lee el backend)
B2_KEY_ID_PUBLICO=<key id del bucket público>
B2_APP_KEY_PUBLICO=<app key del bucket público>
B2_BUCKET_PUBLICO=torio-publico-prod
B2_CDN_URL_PUBLICO=https://torio-publico-prod.s3.us-east-005.backblazeb2.com
```

Protege el archivo (solo lo lee el usuario de servicio):

```bash
sudo chown torio:torio /opt/torio/.env
sudo chmod 600 /opt/torio/.env
```

> **Importante:** usa buckets B2 y credenciales **de producción** distintos a los
> de desarrollo (los del `.env` de dev apuntan a `*-desarrollo`).

---

## 6. Migraciones y datos iniciales

`django-tenants` separa migraciones del schema público y de los tenants.

Los comandos se ejecutan como el usuario `torio` con el Python del venv. Para no
repetir rutas, abre una shell puntual del usuario de servicio:

```bash
sudo -u torio -s
cd /opt/torio
export DJANGO_SETTINGS_MODULE=torioapp.settings.prod
PY=/opt/torio/venv/bin/python

# 1. Migrar el schema público (apps compartidas)
$PY manage.py migrate_schemas --shared

# 2. Crear el tenant público (una sola vez, primera instalación)
$PY manage.py shell <<'PYEOF'
from contenedor.models import CtnCliente, CtnDominio
tenant = CtnCliente(schema_name='public', nombre='Public')
tenant.save(verbosity=1)
CtnDominio.objects.get_or_create(domain='reddocapi2.co', tenant=tenant,
                                 defaults={'is_primary': True})
PYEOF

# 3. Migrar todos los tenants existentes
$PY manage.py migrate_schemas

# 4. Datos de referencia del schema público (idempotente)
$PY manage.py cargar_geodata

# 5. Datos de referencia de los tenants (idempotente)
$PY manage.py cargar_datos_tenant

# 6. Superusuario para el admin (schema público)
$PY manage.py createsuperuser

exit   # salir de la shell del usuario torio
```

> En cada **actualización** que incluya migraciones, ejecutar `migrate_schemas --shared`
> y luego `migrate_schemas` (ver §10).

---

## 7. Archivos estáticos

```bash
sudo -u torio DJANGO_SETTINGS_MODULE=torioapp.settings.prod \
    /opt/torio/venv/bin/python /opt/torio/manage.py collectstatic --noinput
```

Genera `/opt/torio/staticfiles/`, servido por Nginx (ver §9). Repetir en cada
release que cambie estáticos (el admin de Django, Swagger si se habilitara, etc.).

---

## 8. Gunicorn como servicio systemd

El servicio se define en `/etc/systemd/system/torio.service`. Ese directorio es de
root, así que el archivo se escribe con `sudo tee`. Copia y pega el bloque completo,
desde `sudo tee` hasta el `EOF` final:

```bash
sudo tee /etc/systemd/system/torio.service > /dev/null <<'EOF'
[Unit]
Description=Torio API (Gunicorn/Django)
# La BD es externa: solo dependemos de la red, no de un postgresql local.
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=torio
Group=torio
WorkingDirectory=/opt/torio

# Entorno mínimo. El resto de la config la lee la app desde /opt/torio/.env
Environment=DJANGO_SETTINGS_MODULE=torioapp.settings.prod
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

ExecStart=/opt/torio/venv/bin/gunicorn torioapp.wsgi:application \
    --workers 2 \
    --bind 127.0.0.1:8060 \
    --timeout 60 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile -
ExecReload=/bin/kill -s HUP $MAINPID

# Resiliencia
Restart=always
RestartSec=3
TimeoutStopSec=30
UMask=0027

# Endurecimiento (sandbox de systemd)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
EOF

# Comprobar que quedó escrito y que systemd lo entiende
cat /etc/systemd/system/torio.service
sudo systemd-analyze verify /etc/systemd/system/torio.service
```

> **`<<'EOF'` va con comillas simples, a propósito.** Sin ellas, la shell reemplaza
> `$MAINPID` por una cadena vacía al escribir el archivo, y `ExecReload` queda como
> `/bin/kill -s HUP ` — el `reload` de las actualizaciones (§10) fallaría. `sudo tee` (y no
> `sudo cat > archivo`) porque la redirección `>` la hace tu shell, sin permisos de root.
>
> `systemd-analyze verify` no imprime nada si todo está bien. Si ya creaste antes el
> venv (§4), no debe quejarse de `/opt/torio/venv/bin/gunicorn`.
>
> Para editarlo más adelante: `sudo systemctl edit --full torio` (abre el editor y
> recarga al guardar), o repite el `tee` y luego `sudo systemctl daemon-reload`.

Notas profesionales:
- **Workers:** regla práctica `(2 × núcleos) + 1`. Ajusta a la VM.
- **Throttling por worker.** No hay backend de `CACHES`, así que los límites de DRF
  (`DEFAULT_THROTTLE_RATES`) se cuentan en la memoria de cada worker: con 2 workers,
  el `login: 5/min` admite en la práctica hasta 10 intentos por minuto. Lo que tiene que
  limitar de verdad (los intentos del desafío MFA) cuenta en la base de datos.
- **Reciclaje de workers** (`--max-requests` + `--max-requests-jitter`): recicla
  cada worker tras ~1000 peticiones (con jitter para no reiniciarlos a la vez),
  mitigando fugas de memoria en procesos de larga vida.
- `--timeout 60` da margen a operaciones pesadas (importar Excel, generar PDFs);
  `--graceful-timeout 30` deja terminar las peticiones en curso al recargar.
- **Bind a `127.0.0.1:8060`** (solo loopback): Gunicorn escucha en el puerto 8060
  pero **no** queda expuesto a Internet; solo Nginx (o el panel) le hace proxy
  desde la misma máquina. No abras 8060 en el firewall.
- **`ProtectSystem=strict`** deja todo el FS en solo-lectura salvo `/tmp` privado.
  La app no escribe en disco en runtime (logs → journald, archivos → B2, BD
  externa); `PYTHONDONTWRITEBYTECODE=1` evita intentos de escribir `.pyc` bajo el
  árbol de solo-lectura.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now torio
sudo systemctl status torio
# Validar el endurecimiento:
sudo systemd-analyze security torio
```

---

## 8.1 Cola de tareas: RabbitMQ y worker de Celery

Lo que no tiene que esperar a un request va por Celery, con RabbitMQ de broker. Hoy
es una sola tarea: **notificar al adquiriente** cuando el webhook de rededoc avisa
que la DIAN validó un documento (`general/tasks.py`). El webhook solo encola; el
worker arma el PDF y lo manda a rededoc.

Sin el worker corriendo, la validación se guarda igual pero **las facturas no se
notifican**: se quedan en la cola hasta que el worker arranque. Si el broker no
responde, el webhook responde bien, deja un error en el log y esa notificación no
queda encolada: hay que mandarla a mano con `documento/notificar/`.

### RabbitMQ en CloudAMQP

El broker no se instala en el servidor: es una instancia de RabbitMQ en
[CloudAMQP](https://www.cloudamqp.com). En su consola:

1. Crear una instancia **para producción**, en la región más cercana al servidor.
   Desarrollo usa **otra instancia**, nunca la misma: con el mismo vhost, un worker
   de desarrollo tomaría las notificaciones de producción, las correría contra su base
   —donde ese documento no existe—, las confirmaría y se perderían.
2. Copiar la URL **`amqps://`** (con *s*, puerto 5671) de los detalles de la instancia.

En el `.env` (§5):

```
CELERY_BROKER_URL=amqps://<usuario>:<clave>@<host>.cloudamqp.com/<vhost>
```

- La URL lleva la clave: es una credencial, como `REDEDOC_KEY`. Si se filtra, se rota
  desde la consola de CloudAMQP y se reinician `torio` y `torio-celery`.
- Con `amqps://` los settings verifican el certificado **y el nombre** del servidor
  (`CELERY_BROKER_USE_SSL`). No use la URL `amqp://`: el broker está en internet, y
  por ella viajarían la clave y el contenido de las tareas sin cifrar.
- No hay puerto que abrir: el servidor sale hacia CloudAMQP, nadie entra.
- Revise los límites del plan (conexiones simultáneas y mensajes al mes). Para no
  gastarlos en tráfico de control, cada proceso publica por una sola conexión
  (`CELERY_BROKER_POOL_LIMIT = 1`) y el worker arranca sin gossip, mingle ni heartbeat.

### Worker como servicio systemd

```bash
sudo tee /etc/systemd/system/torio-celery.service > /dev/null <<'EOF'
[Unit]
Description=Torio worker de Celery
# El broker es externo (CloudAMQP): solo dependemos de la red.
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=torio
Group=torio
WorkingDirectory=/opt/torio

Environment=DJANGO_SETTINGS_MODULE=torioapp.settings.prod
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

# Dos procesos: las tareas son lentas (PDF y llamadas a rededoc), no intensivas en
# CPU. `-O fair` reparte de a una, junto con el prefetch de 1 de los settings.
# Sin gossip, mingle ni heartbeat: con un solo worker no hay con quién coordinarse,
# y en CloudAMQP ese tráfico de control cuenta contra los mensajes del plan.
# `-Q`: las colas que atiende. Cada tipo de tarea tiene la suya (`CELERY_TASK_ROUTES`),
# y `celery` es la de las tareas sin ruta. Una cola que no esté acá no la atiende nadie:
# al sumar una tarea con cola propia, se agrega aquí o se le da su propio worker.
ExecStart=/opt/torio/venv/bin/celery -A torioapp worker \
    --loglevel=info --concurrency=2 -O fair \
    -Q notificar_documento,celery \
    --without-gossip --without-mingle --without-heartbeat

Restart=always
RestartSec=5
# Deja terminar la tarea en curso antes de matar el proceso. Si se corta igual,
# no se pierde: las tareas se confirman al terminar (`acks_late`) y RabbitMQ la
# vuelve a entregar.
TimeoutStopSec=60
UMask=0027

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now torio-celery
sudo systemctl status torio-celery
```

Para ver qué está haciendo:

```bash
journalctl -u torio-celery -f                     # el log del worker
```

Cuántas tareas esperan en la cola se ve en la consola de CloudAMQP (*RabbitMQ Manager*
→ *Queues*).

---

## 9. Nginx como reverse proxy

Nginx hace proxy al puerto local **`127.0.0.1:8060`** donde escucha Gunicorn. Al
ser TCP en loopback no hay permisos de socket que ajustar.

> ⚠️ **Orden importante (problema huevo-gallina).** Un bloque `server` con
> `ssl_certificate` apuntando a un cert que **aún no existe** hace fallar
> `nginx -t` (`cannot load certificate ... No such file`), y entonces certbot
> tampoco puede recargar Nginx. Por eso se hace en **dos fases**: primero HTTP puro
> para emitir el certificado, luego se añade el bloque TLS.

**Requisitos previos:** DNS de `reddocapi2.co` apuntando a la IP del servidor
y puerto 80 abierto (certbot valida por HTTP-01). Verifica: `dig +short reddocapi2.co`.

### Fase 1 — HTTP puro y emisión del certificado

El sitio se define en `/etc/nginx/sites-available/torio`, un directorio de root, así
que el archivo se escribe con `sudo tee`, igual que el servicio del §8. En esta fase
lleva **solo el bloque HTTP**.

> **Las comillas simples en `<<'EOF'` son obligatorias.** Sin ellas la shell reemplaza
> `$host`, `$remote_addr`, `$scheme` y `$request_uri` por cadenas vacías, y Nginx queda
> reenviando headers vacíos (o, en la fase 2, redirigiendo a `https://`). El dominio
> (`reddocapi2.co`) ya va escrito en los bloques: se pegan tal cual.

Copia y pega el bloque completo, desde `sudo tee` hasta el `EOF` final:

```bash
sudo tee /etc/nginx/sites-available/torio > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name reddocapi2.co;

    location / {
        proxy_pass http://127.0.0.1:8060;   # Gunicorn (backend local único)
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;   # sobrescribe, no concatena (ver notas)
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Comprobar: deben verse las variables ($host, $remote_addr, $scheme) y no huecos
cat /etc/nginx/sites-available/torio
```

Activar el sitio y emitir el certificado:

```bash
# -sf: si el enlace ya existe (segunda pasada), lo reemplaza en vez de fallar
sudo ln -sf /etc/nginx/sites-available/torio /etc/nginx/sites-enabled/torio
sudo rm -f /etc/nginx/sites-enabled/default   # quitar el host por defecto
sudo nginx -t && sudo systemctl reload nginx

# Emitir el certificado (Nginx ya es válido y puede servir el reto ACME)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot certonly --nginx -d reddocapi2.co
ls /etc/letsencrypt/live/reddocapi2.co/  # confirma fullchain.pem y privkey.pem
```

### Fase 2 — Añadir el bloque TLS

Ya con el certificado emitido, **reemplaza** el contenido del archivo por la
versión completa (HTTP→HTTPS + TLS). Es el mismo `sudo tee` sobre el mismo archivo:
`tee` sin `-a` lo sobrescribe entero, así que no queda nada de la fase 1.

```bash
sudo tee /etc/nginx/sites-available/torio > /dev/null <<'EOF'
# HTTP → HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name reddocapi2.co;
    return 301 https://$host$request_uri;
}

server {
    # HTTP/2 en la misma línea `listen` (compatible con Nginx < 1.25.1).
    # En Nginx 1.25.1+ puedes usar la forma nueva: `listen 443 ssl;` + `http2 on;`
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name reddocapi2.co;

    server_tokens off;   # no exponer la versión de Nginx

    # Certificado
    ssl_certificate     /etc/letsencrypt/live/reddocapi2.co/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/reddocapi2.co/privkey.pem;
    # Perfil TLS moderno de Mozilla + DH params (los provee certbot)
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Adjuntos: el límite del backend es 20 MB (el mayor de todos, ver notas)
    client_max_body_size 21M;

    # Timeouts acordes al --timeout de Gunicorn (60s)
    proxy_connect_timeout 10s;
    proxy_read_timeout    60s;
    proxy_send_timeout    60s;

    # Compresión de respuestas JSON de la API
    gzip on;
    gzip_proxied any;
    gzip_types application/json application/javascript text/css;
    gzip_min_length 1024;

    # Estáticos servidos directo por Nginx
    location /static/ {
        alias /opt/torio/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8060;   # Gunicorn (backend local único)
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;   # sobrescribe, no concatena (ver notas)
        proxy_set_header X-Forwarded-Proto $scheme;   # requerido por SECURE_PROXY_SSL_HEADER
        # X-Tenant y Authorization se reenvían tal cual (Nginx no los filtra).
        proxy_redirect off;
    }
}
EOF

# Comprobar antes de recargar
grep -n 'return 301' /etc/nginx/sites-available/torio   # debe decir https://$host$request_uri

# nginx -t valida la sintaxis y que existan los certificados; si falla, NO recarga
# y el Nginx en marcha sigue sirviendo la configuración anterior.
sudo nginx -t && sudo systemctl reload nginx
```

Para editarlo más adelante: `sudo nano /etc/nginx/sites-available/torio` (o repite el
`tee`) y después, siempre, `sudo nginx -t && sudo systemctl reload nginx`.

Notas:
- HSTS, `nosniff`, `X-Frame-Options` y la redirección SSL los emite **Django**
  (`settings/prod.py`) — no se duplican en Nginx para evitar headers repetidos.
- `options-ssl-nginx.conf` y `ssl-dhparams.pem` fijan TLS 1.2/1.3 y cifrados
  modernos (perfil Mozilla). Con `certbot certonly` puede que **no se creen**: si
  `nginx -t` se queja de que faltan, comenta esas dos líneas (TLS sigue operativo)
  o genera el dhparam con `sudo openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048`.
- El `client_max_body_size` debe ser ≥ al **mayor** límite de subida del backend, o
  Nginx corta con 413 antes de que Django pueda responder con su propio mensaje. Hoy
  son: adjuntos 20 MB (`TAMANO_MAXIMO_ARCHIVO` en `general/servicios/archivo.py`),
  importación de Excel 5 MB (`ImportarExcelMixin.MAX_TAMANO_ARCHIVO_BYTES`) e
  imágenes/logotipo 5 MB (`utilidades/imagenes.py`). 21 MB deja margen para la
  envoltura multipart. Si sube alguno de esos límites, sube también este.
- **`X-Forwarded-For` se sobrescribe con `$remote_addr`, no se concatena.** Con
  `CONFIAR_EN_PROXY=True` (§5), `ip_del_request()` (`seguridad/acceso.py`) toma el
  **primer** valor del header como IP del cliente. `$proxy_add_x_forwarded_for` agrega
  la IP real *al final* de lo que mandó el cliente, así que con él cualquiera elige la
  IP que queda en la bitácora de accesos y en los desafíos MFA enviando su propio
  `X-Forwarded-For`. Esto vale mientras Nginx sea el único proxy: si se pone otro
  adelante (Cloudflare, un balanceador), hay que tomar la IP del header que ese proxy
  garantiza (p. ej. `CF-Connecting-IP` con `real_ip_header`) y no la de la conexión.
- Renovación automática del certificado: el timer `certbot.timer` ya viene activo;
  verifícalo con `sudo certbot renew --dry-run`.

---

## 10. Actualizaciones

Las actualizaciones se hacen con un script en el servidor, `/root/actualizar_torio.sh`.
Se crea una sola vez. Como root, copia y pega el bloque completo:

```bash
tee /root/actualizar_torio.sh > /dev/null <<'EOF'
#!/bin/bash
set -e
cd /opt/torio

APP="sudo -u torio env DJANGO_SETTINGS_MODULE=torioapp.settings.prod"

$APP git pull
$APP venv/bin/pip install -r requirements.txt
$APP venv/bin/python manage.py migrate

if [ "$1" = "--fixtures" ] || [ "$1" = "-f" ]; then
    echo "Cargando fixtures..."
    $APP venv/bin/python manage.py cargar_geodata
    $APP venv/bin/python manage.py cargar_datos_tenant
    echo "Fixtures cargados"
fi

$APP venv/bin/python manage.py collectstatic --noinput

systemctl reload torio
# El worker no recarga código en caliente: hay que reiniciarlo. `restart` espera a
# que termine la tarea en curso (TimeoutStopSec) antes de cortar.
systemctl restart torio-celery
EOF

chmod 700 /root/actualizar_torio.sh
```

Para actualizar:

```bash
/root/actualizar_torio.sh              # código, dependencias, migraciones, estáticos
/root/actualizar_torio.sh --fixtures   # lo mismo + recarga los fixtures (o -f)
```

Usa `--fixtures` cuando la actualización traiga cambios en:

- **catálogos** (`*/fixtures/*.json`): países, ciudades, tipos de documento, impuestos…
  Se cargan en el schema público y en **todos** los tenants;
- **grupos y permisos** (`seguridad/grupos.py`): `cargar_geodata` también los
  sincroniza, así que sin `--fixtures` los permisos nuevos no llegan a los grupos.

Sin cambios de ese tipo no hace falta: la carga es idempotente, pero recorre todos los
tenants y es el paso que más tarda a medida que crecen. Los contenedores nuevos no
dependen de esto: su alta siembra sus propios catálogos (§14).

- **`set -e`**: si un paso falla, el script se detiene y no recarga el servicio.
  Corrige el error y vuelve a correrlo; todos los pasos se pueden repetir.
- **`env DJANGO_SETTINGS_MODULE=...`** es necesario: `sudo` borra las variables de
  entorno, y sin ella `manage.py` usa los settings de desarrollo.
- **`migrate`** migra el schema público y todos los tenants (en este proyecto es
  `migrate_schemas`).
- **`reload`** recicla los workers sin cortar el servicio. Si la actualización cambia
  la versión de `gunicorn` o la unidad systemd, usa en su lugar
  `systemctl daemon-reload && systemctl restart torio`.
- **`restart torio-celery`**: el worker de Celery (§8.1) carga el código al arrancar,
  así que sin reiniciarlo seguiría corriendo las tareas con la versión anterior.

---

## 11. Checklist de seguridad pre-producción

```bash
sudo -u torio DJANGO_SETTINGS_MODULE=torioapp.settings.prod \
    /opt/torio/venv/bin/python /opt/torio/manage.py check --deploy
```

No debe reportar ningún aviso `security.W0xx`. Los `drf_spectacular.W001` que aparecen
son del generador de la documentación de la API y no afectan el despliegue.

`settings/prod.py` ya aplica: `DEBUG=False`, `SECURE_SSL_REDIRECT`,
`SESSION/CSRF_COOKIE_SECURE`, HSTS (1 año, subdominios, preload),
`SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY`.

Verifica además:

- [ ] `SECRET_KEY` única y secreta (no la de dev).
- [ ] `DEBUG=False` y `ENABLE_API_DOCS=False`.
- [ ] `ALLOWED_HOSTS` con el host real del backend.
- [ ] `CORS_ALLOWED_ORIGINS` solo con los orígenes del frontend de prod.
- [ ] `AUTH_COOKIE_SECURE=True` y `AUTH_COOKIE_DOMAIN` con punto inicial.
- [ ] Credenciales y buckets B2 **de producción** (no `*-desarrollo`), con la llave
      propia de cada bucket (`B2_KEY_ID`/`B2_APP_KEY` y `B2_KEY_ID_PUBLICO`/`B2_APP_KEY_PUBLICO`).
- [ ] `MFA_ENCRYPTION_KEY` generada para producción (distinta de dev y de `SECRET_KEY`)
      y respaldada fuera del servidor: si se pierde, ningún TOTP se puede descifrar.
- [ ] `CONFIAR_EN_PROXY=True` y Nginx sobrescribiendo `X-Forwarded-For` con
      `$remote_addr` (§9).
- [ ] `/opt/torio/.env` con `chmod 600`, propiedad de `torio`, fuera de git.
- [ ] Servicio corre como usuario de sistema sin login y con el sandbox de systemd
      activo (`systemd-analyze security torio` con score razonable).
- [ ] Firewall del host: solo `80/443` (y `22` restringido) expuestos a Internet.
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
sudo -u torio DJANGO_SETTINGS_MODULE=torioapp.settings.prod \
    /opt/torio/venv/bin/python /opt/torio/manage.py shell \
    -c "import sentry_sdk; sentry_sdk.capture_message('Despliegue Torio OK')"
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

**La vía normal es la API, no el servidor.** Un usuario registrado y verificado crea
su contenedor desde el frontend, que llama a `POST /contenedor/cliente/`. Esa vista
hace todo lo necesario para que el contenedor sirva:

1. crea el `CtnCliente` (y con él el schema, `auto_create_schema=True`) con el
   usuario como `owner`;
2. crea su `CtnDominio` (`<schema>.<TENANT_BASE_DOMAIN>`);
3. lo vincula como miembro propietario, `is_superuser` en ese contenedor y con todos
   los módulos habilitados (`add_user`);
4. le abre la suscripción de prueba (tipo 13, 15 días);
5. tras el commit, siembra catálogos **y datos iniciales** en un hilo aparte
   (`cargar_datos_tenant --schema <schema> --inicial`).

> ⚠️ Crear solo el `CtnCliente` y su dominio **no basta**: sin suscripción,
> `SuscripcionVigente` rechaza todas las peticiones al tenant; sin membresía,
> `EsMiembroDelTenant` también; y sin `--inicial` faltan las semillas editables
> (configuración, etc.).

**Si la carga del paso 5 falla o se corta**, el contenedor queda sin catálogos y solo
queda registrado en el log (`Falló la carga de catálogos del contenedor ...`). Corre en
un hilo del worker, así que un `reload` o una actualización (§10) en ese momento, o el reciclaje
por `--max-requests`, pueden cortarla. Se completa a mano (es idempotente):

```bash
sudo -u torio DJANGO_SETTINGS_MODULE=torioapp.settings.prod \
    /opt/torio/venv/bin/python /opt/torio/manage.py cargar_datos_tenant --schema acme --inicial
```

### Alta desde el servidor (solo si no se puede por la API)

Reproduce los mismos pasos de la vista. El propietario **debe existir** (registrado y
verificado). Ajusta las constantes del principio:

```bash
sudo -u torio -s
cd /opt/torio
export DJANGO_SETTINGS_MODULE=torioapp.settings.prod
PY=/opt/torio/venv/bin/python

$PY manage.py shell <<'PYEOF'
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from contenedor.views.cliente import DIAS_PRUEBA, SUSCRIPCION_TIPO_PRUEBA_ID
from seguridad.models import CAMPOS_ACCESO, SegUsuario

SCHEMA = 'acme'
NOMBRE = 'ACME S.A.'
CELULAR = '3001234567'
CORREO = 'contacto@acme.com'
PROPIETARIO = 'dueno@acme.com'   # debe estar registrado

propietario = SegUsuario.objects.get(email=PROPIETARIO)
tipo = CtnSuscripcionTipo.objects.get(pk=SUSCRIPCION_TIPO_PRUEBA_ID)

with transaction.atomic():
    cliente = CtnCliente.objects.create(
        schema_name=SCHEMA, nombre=NOMBRE, celular=CELULAR, correo=CORREO, owner=propietario,
    )
    CtnDominio.objects.create(
        domain=f'{SCHEMA}.{settings.TENANT_BASE_DOMAIN}', tenant=cliente, is_primary=True,
    )
    cliente.add_user(
        propietario,
        accesos=dict.fromkeys(CAMPOS_ACCESO, True),
        propietario=True,
        is_superuser=True,
    )
    hoy = date.today()
    cliente.suscripcion = CtnSuscripcion.objects.create(
        cliente=cliente,
        usuario=propietario,
        suscripcion_tipo=tipo,
        fecha_inicio=hoy,
        fecha_fin=hoy + timedelta(days=DIAS_PRUEBA),
        frecuencia=CtnSuscripcion.FRECUENCIA_PRUEBA,
    )
    cliente.save(update_fields=['suscripcion'])

print(f'Contenedor {SCHEMA} creado, prueba hasta {cliente.suscripcion.fecha_fin}')
PYEOF

# Catálogos + datos iniciales (--inicial es obligatorio en un alta)
$PY manage.py cargar_datos_tenant --schema acme --inicial
exit
```

El `schema_name` debe ser único, empezar por letra minúscula y contener solo letras,
dígitos y guion bajo. El frontend luego envía `X-Tenant: acme` en sus peticiones.

---

## Resumen rápido (orden de ejecución, primera instalación)

1. Instalar paquetes del sistema (cliente PostgreSQL, sin servidor) (§2)
2. Aprovisionar rol/BD en el PostgreSQL gestionado + abrir conectividad (§3)
3. Crear usuario de sistema `torio` + clonar en `/opt/torio` + venv (§4)
4. Crear `/opt/torio/.env` de producción, incluida `MFA_ENCRYPTION_KEY` (`chmod 600`) (§5)
5. `migrate_schemas --shared` → crear tenant público → `migrate_schemas` (§6)
6. `cargar_geodata` + `cargar_datos_tenant` + `createsuperuser` (§6)
7. `collectstatic` (§7)
8. systemd `torio.service` endurecido + `enable --now` (§8)
9. Nginx (proxy a `127.0.0.1:8060`) + TLS (§9)
10. Firewall (solo 80/443, 22 restringido) + `check --deploy` + `systemd-analyze security` (§11)
