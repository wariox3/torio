# Torio

SaaS multi-tenant construido sobre **Django 5.2** y **PostgreSQL**, con aislamiento por schema vía `django-tenants` y usuarios globales gestionados por `django-tenant-users`.

## Stack

- Python 3.12
- Django 5.2
- PostgreSQL (schema-based multi-tenancy)
- Django REST Framework + SimpleJWT
- `django-tenants` 3.10 · `django-tenant-users` 2.2
- `drf-spectacular`, `django-cors-headers`, `python-decouple`
- `httpx`, `gunicorn`

## Arquitectura

- **`torioapp/`** — configuración del proyecto (settings, URLs, WSGI/ASGI).
- **`contenedor/`** — registro público de inquilinos. Define `CtnCliente` (subclase de `TenantBase`, un schema PostgreSQL por instancia) y `CtnDominio` (mapping host → tenant).
- **`seguridad/`** — usuarios globales (`SegUsuario`, subclase de `UserProfile`). Vive en el schema público; los usuarios pueden pertenecer a varios tenants.
- **`general/`** — lógica de negocio por tenant.
- **`utilidades/`** — servicios transversales: `Zinc` (envío de correos) y `Turnstile` (verificación Cloudflare).

### URLs públicas vs. tenant

- `torioapp/urls_public.py` — schema público (gestión de tenants, autenticación, admin).
- `torioapp/urls_tenant.py` — schema de cada cliente.
- El `host` de la petición decide cuál se sirve, vía `TenantMainMiddleware`.

### Settings por entorno

```
torioapp/settings/
  base.py    # común
  dev.py     # local (DEBUG=True, CORS localhost:4200)
  test.py    # tests (CORS reddoc.uk, Turnstile deshabilitado)
  prod.py    # producción (HTTPS, HSTS, cookies seguras, CORS reddoc.co)
```

`manage.py` usa `torioapp.settings.dev` por defecto. En producción exportar `DJANGO_SETTINGS_MODULE=torioapp.settings.prod` (ya cableado en `wsgi.py`/`asgi.py`).

## Requisitos

- Python 3.12+
- PostgreSQL 14+
- `virtualenv` (recomendado en `~/.venvs/torio`)

## Setup local

```bash
# 1. Clonar y entrar
git clone <repo> torio && cd torio

# 2. Crear y activar entorno virtual
python3.12 -m venv ~/.venvs/torio
source ~/.venvs/torio/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# editar .env con los valores reales

# 5. Crear la base de datos en PostgreSQL
createdb bdtorio

# 6. Migrar
python manage.py migrate_schemas --shared

# 7. Crear el tenant público (una sola vez)
python manage.py shell
# >>> from contenedor.models import CtnCliente, CtnDominio
# >>> tenant = CtnCliente(schema_name='public', nombre='Public')
# >>> tenant.save(verbosity=1)
# >>> CtnDominio.objects.create(domain='localhost', is_primary=True, tenant=tenant)

# 8. Cargar datos iniciales (referencia)
python manage.py cargar_geodata

# 9. Servidor de desarrollo
python manage.py runserver
```

## Variables de entorno

Definidas en `.env` (ver `.env.example`):

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave secreta de Django. Generar con `get_random_secret_key()`. |
| `DEBUG` | `True` solo en dev. |
| `ALLOWED_HOSTS` | CSV de hosts permitidos. |
| `DATABASE_*` | Credenciales PostgreSQL (`USER`, `CLAVE`, `HOST`, `NAME`, `PORT`). |
| `LOG_LEVEL`, `DJANGO_LOG_LEVEL` | Nivel de logging (default `INFO`). |
| `BACKEND_URL` | URL base del backend. |
| `FRONTEND_URL` | URL base del frontend (usada en links de correo). |
| `ZINC_URL` | URL del servicio de envío de correos Zinc. |
| `TURNSTILE_SECRET_KEY` | Secret key de Cloudflare Turnstile. |
| `TURNSTILE_ENABLED` | `True` en prod/test, `False` en dev. |
| `ENABLE_API_DOCS` | Habilita `/api/docs/`. Solo activar en dev/staging. |
| `CORS_ALLOWED_ORIGINS` | Solo en prod. CSV de orígenes permitidos (ej. `https://reddoc.co`). |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | Solo en prod. |

## Endpoints de autenticación

Todos bajo `/seguridad/`:

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `login/` | Inicia sesión. Emite JWT en cookies httpOnly. |
| `POST` | `refresh/` | Renueva el access token. |
| `POST` | `logout/` | Invalida el refresh token y limpia cookies. |
| `POST` | `usuario/` | Registro de usuario. |
| `POST` | `usuario/verificar-email/` | Activa la cuenta con el token del correo. |
| `POST` | `usuario/reenviar-verificacion/` | Reenvía el correo de verificación. |
| `POST` | `usuario/recuperar-clave/` | Envía link de recuperación al correo. |
| `POST` | `usuario/restablecer-clave/` | Establece nueva clave con el token del link. |

Los endpoints de registro, recuperación y login están protegidos con **Cloudflare Turnstile** (campo `turnstile_token` en el body).

## Datos iniciales

El comando `cargar_geodata` carga datos de referencia desde `contenedor/fixtures/` de forma idempotente (`update_or_create`). Los archivos se procesan en orden numérico para respetar las dependencias de FK.

```bash
python manage.py cargar_geodata
```

Salida esperada:

```
01_pais.json (contenedor.CtnPais) — creados: 1, actualizados: 0
02_estado.json (contenedor.CtnEstado) — creados: 33, actualizados: 0
03_ciudad.json (contenedor.CtnCiudad) — creados: 1121, actualizados: 0
04_identificacion.json (contenedor.CtnIdentificacion) — creados: 9, actualizados: 0
05_plan.json (contenedor.CtnPlan) — creados: 11, actualizados: 0
```

### Fixtures disponibles

| Archivo | Modelo | Registros | Descripción |
|---|---|---|---|
| `01_pais.json` | `CtnPais` | 1 | Colombia |
| `02_estado.json` | `CtnEstado` | 33 | Departamentos de Colombia |
| `03_ciudad.json` | `CtnCiudad` | 1121 | Municipios de Colombia |
| `04_identificacion.json` | `CtnIdentificacion` | 9 | Tipos de identificación DIAN |
| `05_plan.json` | `CtnPlan` | 11 | Planes de suscripción |

### Formato de fixture

Cada archivo JSON sigue esta estructura:

```json
{
  "model": "app.NombreModelo",
  "data": [
    { "id": 1, "campo": "valor", "fk_id": "referencia" }
  ]
}
```

- El prefijo numérico (`01_`, `02_`, …) define el orden de carga para respetar las FK.
- Los campos FK usan el sufijo `_id` (ej. `pais_id`, `estado_id`).
- El comando es idempotente: se puede ejecutar varias veces sin duplicar datos.

## Comandos útiles

```bash
python manage.py runserver                  # dev server
python manage.py migrate_schemas --shared   # migraciones del schema público
python manage.py migrate_schemas            # migraciones de todos los tenants
python manage.py makemigrations             # generar migraciones
python manage.py cargar_geodata             # cargar datos de referencia
python manage.py check --deploy             # auditoría de seguridad para prod
python manage.py createsuperuser            # admin (en schema público)
python manage.py test                       # tests
```

## Crear un nuevo tenant

```python
from contenedor.models import CtnCliente, CtnDominio

cliente = CtnCliente.objects.create(schema_name='acme', nombre='ACME S.A.')
CtnDominio.objects.create(domain='acme.midominio.com', tenant=cliente, is_primary=True)
```

El schema PostgreSQL se crea automáticamente (`auto_create_schema=True`). El `schema_name` debe ser único, comenzar con letra minúscula y contener solo letras, dígitos y guion bajo.

## Convenciones

- **Modelos** con prefijo de app (`Ctn*`, `Seg*`) y `db_table` explícito en `Meta`.
- **Settings** nunca con secretos hardcodeados — siempre vía `python-decouple`.
- **Migraciones** del schema público con `migrate_schemas --shared`; las de tenants con `migrate_schemas` (todos) o `migrate_schemas --schema=acme`.

## Pendiente

- Tests (`pytest` + `pytest-django`).
- CI (lint + tests + check de migraciones).
- Docker / `docker-compose` para PostgreSQL local + app.
- `pre-commit` con `ruff` / `black`.
- Tareas asíncronas (Celery + Redis) para aprovisionamiento de tenants.
