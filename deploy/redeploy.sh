#!/usr/bin/env bash
#
# Redespliegue de Torio en producción.
#
# Ejecuta los pasos de actualización como el usuario de servicio (torio) y recarga
# el servicio systemd. Idempotente: se puede correr varias veces sin problema.
#
# Uso (como root):
#     sudo /opt/torio/app/deploy/redeploy.sh
#
set -euo pipefail

# ── Configuración (ajusta si cambian las rutas) ─────────────────────────────
APP_DIR=/opt/torio/app
VENV=/opt/torio/venv
SERVICE=torio
RUN_USER=torio
SETTINGS=torioapp.settings.prod

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# Debe correr como root para poder recargar el servicio systemd.
if [[ ${EUID} -ne 0 ]]; then
    echo "Este script debe ejecutarse como root:  sudo $0" >&2
    exit 1
fi

# Ejecuta un comando como el usuario de servicio, dentro del dir de la app y con
# el settings de producción exportado.
as_app() {
    sudo -u "${RUN_USER}" env DJANGO_SETTINGS_MODULE="${SETTINGS}" \
        bash -c "cd '${APP_DIR}' && $*"
}

log "Actualizando código (git pull)"
as_app "git pull --ff-only"

log "Instalando dependencias"
as_app "'${VENV}/bin/pip' install -q -r requirements.txt"

log "Migraciones del schema público"
as_app "'${VENV}/bin/python' manage.py migrate_schemas --shared"

log "Migraciones de los tenants"
as_app "'${VENV}/bin/python' manage.py migrate_schemas"

log "Datos de referencia (público + tenants, idempotente)"
as_app "'${VENV}/bin/python' manage.py cargar_geodata"
as_app "'${VENV}/bin/python' manage.py cargar_datos_tenant"

log "Recolectando estáticos"
as_app "'${VENV}/bin/python' manage.py collectstatic --noinput"

# Asocia este despliegue a su release en Sentry (SHA de git). Reescribe la línea
# completa, sin comentarios inline (python-decouple no los admite).
log "Registrando SENTRY_RELEASE en .env"
REV="$(as_app 'git rev-parse --short HEAD')"
as_app "if grep -q '^SENTRY_RELEASE=' .env; then \
            sed -i 's/^SENTRY_RELEASE=.*/SENTRY_RELEASE=${REV}/' .env; \
        else \
            printf 'SENTRY_RELEASE=%s\n' '${REV}' >> .env; \
        fi"

# reload (HUP) recicla los workers sin downtime. Tras migraciones de schema
# incompatibles con la versión anterior, cambia a 'restart'.
log "Recargando el servicio ${SERVICE}"
systemctl reload "${SERVICE}" || systemctl restart "${SERVICE}"

log "Despliegue completado (release ${REV}). Estado del servicio:"
systemctl --no-pager --lines=0 status "${SERVICE}" || true
