# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Activate the virtual environment before running any command:

```bash
source /home/desarrollo/.venvs/torio/bin/activate
```

```bash
python manage.py runserver                            # Start dev server
python manage.py migrate                              # Apply migrations
python manage.py makemigrations                       # Generate migrations
python manage.py cargar_geodata                       # Load public-schema reference data from contenedor/fixtures/ (idempotent)
python manage.py cargar_datos_tenant                  # Load tenant reference data into all tenant schemas (idempotent)
python manage.py cargar_datos_tenant --schema demo    # Load tenant reference data into a specific schema
python manage.py test                                 # Run all tests
python manage.py test contenedor                      # Run tests for a specific app
python manage.py createsuperuser                      # Create admin user
```

## Architecture

This is a **Django 5.2.13** multi-tenant SaaS project using **PostgreSQL schema-based tenancy** via `django-tenants` and `django-tenant-users`.

### Apps

- **`torioapp/`** — Django project config (settings, root URLs, WSGI/ASGI)
- **`contenedor/`** — Shared (public schema). Tenant registry: `CtnCliente` (`TenantBase` subclass) maps each tenant to a PostgreSQL schema. `auto_create_schema = True` creates the schema on save.
- **`seguridad/`** — Shared (public schema). Authentication and user management.
- **`general/`** — Tenant app. Core reference models (contacts, cities, banks, etc.) isolated per tenant.
- **`contabilidad/`** — Tenant app. Accounting models (chart of accounts, etc.) isolated per tenant.

### Multi-tenancy model

Each `CtnCliente` owns a separate PostgreSQL schema. The `TenantMainMiddleware` resolves the tenant from the request `Host` header by looking up the domain in `CtnDominio`.

- **Public schema** (`localhost`) → `torioapp/urls_public.py` → `contenedor/`, `seguridad/`
- **Tenant schema** (`<schema>.localhost`) → `torioapp/urls_tenant.py` → `general/`, `contabilidad/`

`SHARED_APPS` run in the public schema. `TENANT_APPS` run in each tenant's isolated schema.

### Fixture system

Two separate fixture loaders, both idempotent (`update_or_create`):

**Public schema** — `python manage.py cargar_geodata`
- Reads from `contenedor/fixtures/*.json`
- Loads into the public schema

**Tenant schemas** — `python manage.py cargar_datos_tenant`
- Reads from `general/fixtures/*.json`
- Loads into every tenant schema (or one with `--schema <name>`)

Both use the same JSON format:

```json
{
  "model": "general.GenPais",
  "data": [
    { "id": "CO", "nombre": "Colombia", "codigo": "169" }
  ]
}
```

Optional field `"actualizar_secuencia": true` resets the PostgreSQL sequence after loading — use this when the model has a manual `BigIntegerField(primary_key=True)` and the next auto-generated PK could collide.

Optional field `"solo_crear": true` (tenant loader only) inserts each row **only if it doesn't already exist** (`get_or_create`) and never overwrites it on later runs — use this for tenant-editable singletons/config seeded once at tenant creation (e.g. `GenConfiguracion`), so re-running `cargar_datos_tenant` for other catalogs doesn't clobber the tenant's edits.

### Development notes

- Cookie domain is set to `.localhost` so JWT cookies work across all tenant subdomains.
- In `DEBUG=True`, the login response includes `access_token` in the body for Postman testing.
- Add `.localhost` to `ALLOWED_HOSTS` in `.env` to accept all tenant subdomains locally.
