# Torio

SaaS multi-tenant construido sobre **Django 6** y **PostgreSQL**, con aislamiento por schema vía `django-tenants` y usuarios globales gestionados por `django-tenant-users`.

## Stack

- Python 3.12
- Django 6.0
- PostgreSQL (schema-based multi-tenancy)
- Django REST Framework
- `django-tenants` 3.10 · `django-tenant-users` 2.2
- `django-cors-headers`, `python-decouple`

## Arquitectura

- **`torioapp/`** — configuración del proyecto (settings, URLs, WSGI/ASGI).
- **`contenedor/`** — registro público de inquilinos. Define `CtnCliente` (subclase de `TenantBase`, un schema PostgreSQL por instancia) y `CtnDominio` (mapping host → tenant).
- **`seguridad/`** — usuarios globales (`SegUsuario`, subclase de `UserProfile`). Vive en el schema público; los usuarios pueden pertenecer a varios tenants.

### URLs públicas vs. tenant

- `torioapp/urls_public.py` — schema público (gestión de tenants, super-admin).
- `torioapp/urls_tenant.py` — schema de cada cliente.
- El `host` de la petición decide cuál se sirve, vía `TenantMainMiddleware`.

### Settings por entorno

```
torioapp/settings/
  base.py    # común
  dev.py     # local (DEBUG=True, CORS abierto, email a consola)
  prod.py    # producción (HTTPS, HSTS, cookies seguras, CORS estricto)
  test.py    # tests (hashing rápido)
```

`manage.py` usa `torioapp.settings.dev` por defecto. En producción, exportar `DJANGO_SETTINGS_MODULE=torioapp.settings.prod` (ya cableado en `wsgi.py`/`asgi.py`).

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
# >>> public = CtnCliente.objects.create(schema_name='public', nombre='Public')
# >>> CtnDominio.objects.create(domain='localhost', tenant=public, is_primary=True)

# 8. Servidor de desarrollo
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
| `CORS_ALLOWED_ORIGINS` | Solo en prod. CSV de orígenes permitidos. |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | Solo en prod. |

## Comandos útiles

```bash
python manage.py runserver                  # dev server
python manage.py migrate_schemas --shared   # migraciones del schema público
python manage.py migrate_schemas            # migraciones de todos los tenants
python manage.py makemigrations             # generar migraciones
python manage.py check --deploy             # auditoría de seguridad para prod
python manage.py createsuperuser            # admin (en schema público)
python manage.py test                       # tests
```

## Crear un nuevo tenant

```python
from contenedor.models import CtnCliente, CtnDominio

cliente = CtnCliente.objects.create(schema_name='acme', nombre='ACME S.A.')
CtnDominio.objects.create(domain='acme.localhost', tenant=cliente, is_primary=True)
```

El schema PostgreSQL se crea automáticamente (`auto_create_schema=True`).

## Convenciones

- **Modelos** con prefijo de app (`Ctn*`, `Seg*`) y `db_table` explícito en `Meta`.
- **Settings** nunca con secretos hardcodeados — siempre vía `python-decouple`.
- **Migraciones** del schema público se aplican con `migrate_schemas --shared`; las de tenants con `migrate_schemas` (todos) o `migrate_schemas --schema=acme`.

## Pendiente

- Tests (`pytest` + `pytest-django`).
- CI (lint + tests + check de migraciones).
- Docker / `docker-compose` para PostgreSQL local + app.
- `pre-commit` con `ruff` / `black`.
- Documentación de API (`drf-spectacular`).
- Tareas asíncronas (Celery + Redis) para aprovisionamiento de tenants y emails.
