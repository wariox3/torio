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

### Authentication and MFA

Login lives in the **public schema** (`seguridad/views/autenticacion.py`) and issues JWTs in
httpOnly cookies, with rotation and blacklist. Two things are easy to get wrong:

- **MFA belongs to the account, not the tenant.** All four `SegMfa*` models live in the
  public schema. Nothing about MFA touches `contenedor/` or a tenant schema, and there is no
  endpoint to administer another user's MFA — not even for a container owner.
- **`POST /seguridad/login/` does not always issue tokens.** If the account has MFA active and
  the browser is not remembered, it returns `{mfa_requerido, mfa_token, metodo}` and the
  session is only issued by `POST /seguridad/login/mfa/`.

Three methods, offered in this order: **SMS**, **email** (both send a code through `Zinc()`
and share the `METODOS_ENVIADOS` path) and **TOTP** (`pyotp`, no delivery involved). SMS
reads `SegUsuario.celular`, which is free text, so it goes through `celular_para_sms()` —
Zinc requires exactly 10 digits.

All the mechanics (challenges, codes, backup codes, remembered devices) live in
`seguridad/mfa.py`; views only translate `MfaError` into an HTTP response. Requires `MFA_ENCRYPTION_KEY` in `.env` — a Fernet key, deliberately separate
from `SECRET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Session lifetimes: access 15 min, refresh 1 day (an *inactivity* timeout — rotation slides
it), and `SESION_MAXIMA` 30 days as an absolute cap carried in the custom `ses` claim, so
every session eventually goes back through `/login/`, the only place MFA is verified.

Full design and rationale: **`docs/mfa.md`**.

### Development notes

- Cookie domain is set to `.localhost` so JWT cookies work across all tenant subdomains.
- In `DEBUG=True`, the login response includes `access_token` in the body for Postman testing.
- Add `.localhost` to `ALLOWED_HOSTS` in `.env` to accept all tenant subdomains locally.
- There is no `CACHES` backend configured, so DRF throttling counts **per gunicorn worker**.
  Anything that must actually limit attempts (like the MFA challenge) counts in the database,
  not in the cache.
