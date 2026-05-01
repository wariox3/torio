# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Activate the virtual environment before running any command:

```bash
source /home/desarrollo/.venvs/torio/bin/activate
```

```bash
python manage.py runserver          # Start dev server
python manage.py migrate            # Apply migrations
python manage.py makemigrations     # Generate migrations
python manage.py test               # Run all tests
python manage.py test contenedor    # Run tests for a specific app
python manage.py createsuperuser    # Create admin user
```

## Architecture

This is a **Django 5.2.13** multi-tenant SaaS project using **PostgreSQL schema-based tenancy** via `django-tenants` and `django-tenant-users`.

**Key dependency**: `django-tenants` requires **PostgreSQL** — SQLite (currently in `settings.py`) is a placeholder and will not work for tenant features. The database engine must be changed to `django.db.backends.postgresql` before running any tenant-related code.

### Apps

- **`torioapp/`** — Django project config (settings, root URLs, WSGI/ASGI)
- **`contenedor/`** — Tenant management. Holds the `Cliente` model (`TenantBase` subclass) which maps each tenant to a PostgreSQL schema. `auto_create_schema = True` means schema is created on `Cliente.save()`.
- **`seguridad/`** — Security/auth app (scaffold only, not yet implemented)

### Multi-tenancy model

`Cliente` (in `contenedor/models/cliente.py`) is the public-schema tenant registry. Each `Cliente` instance owns a separate PostgreSQL schema, isolating its data. `django-tenant-users` extends this to provide global user accounts that can belong to multiple tenants.

To wire up tenancy, `settings.py` will need:
- `DATABASE_ROUTERS` with `django_tenants` router
- `TENANT_MODEL = 'contenedor.Cliente'`
- `TENANT_DOMAIN_MODEL` pointing to a domain model
- Separation of `SHARED_APPS` vs `TENANT_APPS` in `INSTALLED_APPS`
